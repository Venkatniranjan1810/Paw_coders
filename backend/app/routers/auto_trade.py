"""Auto-buy / auto-sell condition API routes."""
from decimal import Decimal
from typing import Annotated, Optional

from app.models import auto_trade as auto_trade_model
from app.models import holding as holding_model
from app.models import portfolio as portfolio_model
from app.models import stock as stock_model
from app.routers.utils import require_portfolio_exists
from app.schemas.auto_trade import (
    AutoTradeCheckResult,
    AutoTradeCondition,
    AutoTradeConditionCreate,
    AutoTradeConditionListResponse,
    AutoTradeConditionUpdate,
    AutoTradeHoldingRulePayload,
    AutoTradeStatus,
)
from app.services import auto_trade as auto_trade_service
from fastapi import APIRouter, HTTPException, Query, status

router = APIRouter(prefix="/portfolios/{portfolio_id}/auto-trade-conditions", tags=["Auto Trade"])


def _require_condition(portfolio_id: int, condition_id: int) -> dict:
    condition = auto_trade_model.get_condition(condition_id)
    if condition is None or condition["portfolio_id"] != portfolio_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Auto-trade condition {condition_id} not found for portfolio {portfolio_id}",
        )
    return condition


@router.post(
    "",
    response_model=AutoTradeCondition,
    status_code=status.HTTP_201_CREATED,
    summary="Create an auto-buy/auto-sell condition",
)
@require_portfolio_exists
def create_condition(portfolio_id: int, payload: AutoTradeConditionCreate):
    """Create a condition that auto-executes a buy/sell once the stock price
    crosses the given threshold, and alerts the user when it fires."""
    if stock_model.get_stock_by_id(payload.stock_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stock {payload.stock_id} not found",
        )
    portfolio = portfolio_model.get_portfolio_by_id(portfolio_id)
    condition_id = auto_trade_model.insert_condition(
        {
            "portfolio_id": portfolio_id,
            "stock_id": payload.stock_id,
            "user_id": portfolio["user_id"],
            "action": payload.action.value,
            "operator": payload.operator.value,
            "threshold_price": payload.threshold_price,
            "quantity": payload.quantity,
        }
    )
    return auto_trade_model.get_condition(condition_id)


@router.get(
    "",
    response_model=AutoTradeConditionListResponse,
    summary="List a portfolio's auto-trade conditions",
)
@require_portfolio_exists
def list_conditions(
    portfolio_id: int,
    condition_status: Annotated[Optional[AutoTradeStatus], Query(alias="status")] = None,
):
    """Return the portfolio's auto-trade conditions, optionally filtered by status."""
    status_value = condition_status.value if condition_status is not None else None
    conditions = auto_trade_model.list_conditions(portfolio_id=portfolio_id, status=status_value)
    return {"conditions": conditions}


@router.get(
    "/{condition_id}",
    response_model=AutoTradeCondition,
    summary="Get a single auto-trade condition",
)
@require_portfolio_exists
def get_condition(portfolio_id: int, condition_id: int):
    """Return one auto-trade condition belonging to the portfolio."""
    return _require_condition(portfolio_id, condition_id)


@router.patch(
    "/{condition_id}",
    response_model=AutoTradeCondition,
    summary="Update an auto-trade condition",
)
@require_portfolio_exists
def update_condition(portfolio_id: int, condition_id: int, payload: AutoTradeConditionUpdate):
    """Patch the action, operator, threshold price, and/or quantity of a condition."""
    _require_condition(portfolio_id, condition_id)
    fields = payload.model_dump(exclude_unset=True)
    if "action" in fields and fields["action"] is not None:
        fields["action"] = fields["action"].value if hasattr(fields["action"], "value") else fields["action"]
    if "operator" in fields and fields["operator"] is not None:
        fields["operator"] = fields["operator"].value if hasattr(fields["operator"], "value") else fields["operator"]
    auto_trade_model.update_condition(condition_id, fields)
    return auto_trade_model.get_condition(condition_id)


@router.delete(
    "/{condition_id}",
    response_model=AutoTradeCondition,
    summary="Cancel/delete an auto-trade condition",
)
@require_portfolio_exists
def delete_condition(portfolio_id: int, condition_id: int):
    """Cancel a condition so it no longer triggers. The row is kept for audit history."""
    _require_condition(portfolio_id, condition_id)
    auto_trade_model.cancel_condition(condition_id)
    return auto_trade_model.get_condition(condition_id)


@router.post(
    "/holding-rules",
    response_model=list[AutoTradeCondition],
    status_code=status.HTTP_201_CREATED,
    summary="Create or update stop-loss and take-profit rules for a holding",
)
@require_portfolio_exists
def upsert_holding_rules(portfolio_id: int, payload: AutoTradeHoldingRulePayload):
    """Replace the active sell rules for a holding with the supplied stop-loss and take-profit values."""
    if stock_model.get_stock_by_id(payload.stock_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stock {payload.stock_id} not found",
        )

    holding = holding_model.get_holding(portfolio_id, payload.stock_id)
    if holding is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Holding for stock {payload.stock_id} not found in portfolio {portfolio_id}",
        )

    entry_price = Decimal(str(holding.get("avg_buy_price") or 0))
    if entry_price <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Average buy price is unavailable for this holding",
        )

    for existing in auto_trade_model.list_active_conditions_for_portfolio_stock(portfolio_id, payload.stock_id):
        auto_trade_model.cancel_condition(existing["condition_id"])

    created_conditions: list[dict] = []
    quantity = Decimal(payload.quantity or holding.get("quantity") or 0)

    if payload.stop_loss_percent is not None and payload.stop_loss_percent > 0:
        threshold = auto_trade_service.calculate_rule_target_price(entry_price, "stop_loss", payload.stop_loss_percent)
        condition_id = auto_trade_model.insert_condition(
            {
                "portfolio_id": portfolio_id,
                "stock_id": payload.stock_id,
                "user_id": portfolio_model.get_portfolio_by_id(portfolio_id)["user_id"],
                "action": "SELL",
                "operator": "<=",
                "threshold_price": threshold,
                "quantity": quantity,
            }
        )
        created_conditions.append(auto_trade_model.get_condition(condition_id))

    if payload.take_profit_percent is not None and payload.take_profit_percent > 0:
        threshold = auto_trade_service.calculate_rule_target_price(entry_price, "take_profit", payload.take_profit_percent)
        condition_id = auto_trade_model.insert_condition(
            {
                "portfolio_id": portfolio_id,
                "stock_id": payload.stock_id,
                "user_id": portfolio_model.get_portfolio_by_id(portfolio_id)["user_id"],
                "action": "SELL",
                "operator": ">=",
                "threshold_price": threshold,
                "quantity": quantity,
            }
        )
        created_conditions.append(auto_trade_model.get_condition(condition_id))

    return created_conditions


@router.post(
    "/check",
    response_model=AutoTradeCheckResult,
    summary="Manually run the auto-trade check for this portfolio",
)
@require_portfolio_exists
def run_check(portfolio_id: int):
    """Evaluate this portfolio's active conditions against current prices now,
    instead of waiting for the next periodic price-refresh cycle."""
    return auto_trade_service.run_auto_trade_check_for_portfolio(portfolio_id)
