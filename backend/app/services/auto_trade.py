"""Auto-buy / auto-sell condition evaluation and execution.

Conditions are evaluated whenever fresh prices are available (piggybacked on
the periodic price-refresh cycle, see app/services/price_refresh.py). When a
condition's operator/threshold matches the observed price, the corresponding
buy/sell is executed via the existing atomic holdings logic and the user is
notified through the existing alerts system.
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from app.models import alerts as alerts_model
from app.models import auto_trade as auto_trade_model
from app.models import holding as holding_model
from app.models import stock as stock_model
from app.models import transaction as transaction_model

_OPERATORS = {
    "<": lambda observed, threshold: observed < threshold,
    "<=": lambda observed, threshold: observed <= threshold,
    ">": lambda observed, threshold: observed > threshold,
    ">=": lambda observed, threshold: observed >= threshold,
    "=": lambda observed, threshold: observed == threshold,
}


def condition_met(operator: str, observed_price: Decimal, threshold: Decimal) -> bool:
    """True when the observed price satisfies the condition's operator/threshold."""
    comparator = _OPERATORS.get(operator)
    if comparator is None:
        raise ValueError(f"Unsupported operator: {operator}")
    return comparator(Decimal(observed_price), Decimal(threshold))


def _alert_for(condition: dict[str, Any], observed_price: Decimal, message: str, severity: str) -> dict[str, Any]:
    return {
        "portfolio_id": condition["portfolio_id"],
        "user_id": condition["user_id"],
        "category": "auto_trade",
        "severity": severity,
        "metric": condition.get("symbol") or str(condition["stock_id"]),
        "observed_value": observed_price,
        "threshold": condition["threshold_price"],
        "message": message,
    }


def execute_condition(condition: dict[str, Any], observed_price: Decimal) -> dict[str, Any]:
    """Execute the buy/sell for a triggered condition and record the outcome.

    On success the condition is deactivated (status='triggered') and a success
    alert is stored. On a funds/quantity failure the condition stays active so
    it can retry on the next check cycle, and a failure alert is stored.
    """
    symbol = condition.get("symbol") or str(condition["stock_id"])
    quantity = Decimal(condition["quantity"])

    try:
        if condition["action"] == "BUY":
            holding_model.buy_stock(condition["portfolio_id"], condition["stock_id"], quantity, observed_price)
            latest = transaction_model.get_transactions(
                condition["portfolio_id"], trans_type="BUY", limit=1
            )
            trans_id = latest[0]["trans_id"] if latest else None
        else:
            sold = holding_model.sell_stock(condition["portfolio_id"], condition["stock_id"], observed_price, quantity)
            trans_id = sold.get("trans_id")
    except (holding_model.InsufficientFundsError, holding_model.InsufficientQuantityError) as exc:
        auto_trade_model.mark_check_failed(condition["condition_id"], str(exc))
        message = (
            f"Auto-{condition['action']} of {quantity} {symbol} failed at ${observed_price}: {exc}"
        )
        alert = alerts_model.get_alert(
            alerts_model.insert_alert(_alert_for(condition, observed_price, message, "warning"))
        )
        return {"condition_id": condition["condition_id"], "status": "failed", "error": str(exc), "alert": alert}

    auto_trade_model.mark_triggered(condition["condition_id"], trans_id)

    message = f"Auto-{condition['action']} of {quantity} {symbol} executed at ${observed_price}."
    alert = alerts_model.get_alert(
        alerts_model.insert_alert(_alert_for(condition, observed_price, message, "info"))
    )
    return {"condition_id": condition["condition_id"], "status": "triggered", "alert": alert}


def evaluate_conditions_for_stock(stock_id: int, observed_price: Decimal) -> list[dict[str, Any]]:
    """Check every active condition for a stock against its latest price."""
    results: list[dict[str, Any]] = []
    for condition in auto_trade_model.list_active_conditions_for_stock(stock_id):
        if condition_met(condition["operator"], observed_price, condition["threshold_price"]):
            results.append(execute_condition(condition, observed_price))
        else:
            auto_trade_model.touch_last_checked(condition["condition_id"])
    return results


def run_auto_trade_check_for_all_active(
    prices: Optional[dict[int, Decimal]] = None,
) -> dict[str, Any]:
    """Evaluate all active conditions across every stock that has one.

    Args:
        prices: optional pre-fetched {stock_id: close_price} map (e.g. from a
            price-refresh cycle) to avoid re-querying prices. Falls back to
            the latest stored quote per stock when not provided.
    """
    stock_ids = auto_trade_model.list_distinct_active_stock_ids()
    checked = 0
    triggered = 0
    failed = 0

    for stock_id in stock_ids:
        price = (prices or {}).get(stock_id)
        if price is None:
            quote = stock_model.get_latest_quote(stock_id)
            if quote is None or quote.get("price") is None:
                continue
            price = Decimal(str(quote["price"]))

        for result in evaluate_conditions_for_stock(stock_id, price):
            checked += 1
            if result["status"] == "triggered":
                triggered += 1
            else:
                failed += 1

    return {
        "conditions_checked": checked,
        "triggered": triggered,
        "failed": failed,
        "checked_at": datetime.now(timezone.utc),
    }


def run_auto_trade_check_for_portfolio(portfolio_id: int) -> dict[str, Any]:
    """Evaluate active conditions belonging to a single portfolio (manual trigger)."""
    checked = 0
    triggered = 0
    failed = 0

    for condition in auto_trade_model.list_conditions(portfolio_id=portfolio_id, status="active"):
        quote = stock_model.get_latest_quote(condition["stock_id"])
        if quote is None or quote.get("price") is None:
            continue
        price = Decimal(str(quote["price"]))
        if condition_met(condition["operator"], price, condition["threshold_price"]):
            result = execute_condition(condition, price)
            checked += 1
            if result["status"] == "triggered":
                triggered += 1
            else:
                failed += 1
        else:
            auto_trade_model.touch_last_checked(condition["condition_id"])
            checked += 1

    return {
        "conditions_checked": checked,
        "triggered": triggered,
        "failed": failed,
        "checked_at": datetime.now(timezone.utc),
    }
