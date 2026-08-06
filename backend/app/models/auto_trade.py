"""Auto-trade condition SQL queries / data-access functions."""
from typing import Any, Optional

from app.database import execute, fetch_all, fetch_one, insert

# --- SQL statements -------------------------------------------------------

_SELECT_CONDITION_BASE = """
    SELECT c.condition_id, c.portfolio_id, c.stock_id, s.symbol, s.short_name,
           c.user_id, c.action, c.operator, c.threshold_price, c.quantity,
           c.status, c.last_checked_at, c.last_error, c.triggered_at,
           c.trans_id, c.created_at, c.updated_at
    FROM auto_trade_conditions c
    JOIN stocks s ON s.stock_id = c.stock_id
"""

_SELECT_CONDITION_BY_ID = _SELECT_CONDITION_BASE + " WHERE c.condition_id = %s"

_INSERT_CONDITION = """
    INSERT INTO auto_trade_conditions
        (portfolio_id, stock_id, user_id, action, operator, threshold_price, quantity)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
"""

_SELECT_ACTIVE_CONDITIONS_FOR_STOCK = _SELECT_CONDITION_BASE + """
    WHERE c.stock_id = %s AND c.status = 'active'
"""

_UPDATE_TRIGGERED = """
    UPDATE auto_trade_conditions
    SET status = 'triggered', trans_id = %s, triggered_at = NOW(),
        last_checked_at = NOW(), last_error = NULL
    WHERE condition_id = %s
"""

_UPDATE_CHECK_FAILED = """
    UPDATE auto_trade_conditions
    SET last_error = %s, last_checked_at = NOW()
    WHERE condition_id = %s
"""

_UPDATE_LAST_CHECKED = """
    UPDATE auto_trade_conditions
    SET last_checked_at = NOW()
    WHERE condition_id = %s
"""

_UPDATE_CANCEL = """
    UPDATE auto_trade_conditions
    SET status = 'cancelled'
    WHERE condition_id = %s
"""

_SELECT_DISTINCT_ACTIVE_STOCK_IDS = """
    SELECT DISTINCT stock_id FROM auto_trade_conditions WHERE status = 'active'
"""


# --- Data-access functions ------------------------------------------------

def get_condition(condition_id: int) -> Optional[dict[str, Any]]:
    """Return a single auto-trade condition by id, or None."""
    return fetch_one(_SELECT_CONDITION_BY_ID, (condition_id,))


def insert_condition(condition: dict[str, Any]) -> int:
    """Persist a new auto-trade condition and return its new condition_id."""
    return insert(
        _INSERT_CONDITION,
        (
            condition["portfolio_id"],
            condition["stock_id"],
            condition["user_id"],
            condition["action"],
            condition["operator"],
            condition["threshold_price"],
            condition["quantity"],
        ),
    )


def list_conditions(
    portfolio_id: Optional[int] = None,
    status: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Return auto-trade conditions, optionally filtered by portfolio and/or status."""
    query = _SELECT_CONDITION_BASE
    conditions: list[str] = []
    params: list[Any] = []

    if portfolio_id is not None:
        conditions.append("c.portfolio_id = %s")
        params.append(portfolio_id)
    if status is not None:
        conditions.append("c.status = %s")
        params.append(status)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY c.created_at DESC, c.condition_id DESC"

    return fetch_all(query, tuple(params))


def list_active_conditions_for_stock(stock_id: int) -> list[dict[str, Any]]:
    """Return all currently-active conditions targeting a given stock."""
    return fetch_all(_SELECT_ACTIVE_CONDITIONS_FOR_STOCK, (stock_id,))


def list_distinct_active_stock_ids() -> list[int]:
    """Return the stock_ids that have at least one active condition."""
    rows = fetch_all(_SELECT_DISTINCT_ACTIVE_STOCK_IDS)
    return [int(row["stock_id"]) for row in rows]


def update_condition(condition_id: int, fields: dict[str, Any]) -> bool:
    """Patch mutable fields (action, operator, threshold_price, quantity).

    Returns True when a row was updated.
    """
    allowed = {"action", "operator", "threshold_price", "quantity"}
    updates = {key: value for key, value in fields.items() if key in allowed and value is not None}
    if not updates:
        return True
    set_clause = ", ".join(f"{key} = %s" for key in updates)
    params = list(updates.values()) + [condition_id]
    return execute(f"UPDATE auto_trade_conditions SET {set_clause} WHERE condition_id = %s", tuple(params)) > 0


def cancel_condition(condition_id: int) -> bool:
    """Mark a condition as cancelled. Returns True when a row was updated."""
    return execute(_UPDATE_CANCEL, (condition_id,)) > 0


def mark_triggered(condition_id: int, trans_id: int) -> bool:
    """Mark a condition as successfully triggered (one-shot deactivation)."""
    return execute(_UPDATE_TRIGGERED, (trans_id, condition_id)) > 0


def mark_check_failed(condition_id: int, error: str) -> bool:
    """Record a failed trigger attempt without deactivating the condition."""
    return execute(_UPDATE_CHECK_FAILED, (error, condition_id)) > 0


def touch_last_checked(condition_id: int) -> bool:
    """Record that a condition was checked (no match this cycle)."""
    return execute(_UPDATE_LAST_CHECKED, (condition_id,)) > 0
