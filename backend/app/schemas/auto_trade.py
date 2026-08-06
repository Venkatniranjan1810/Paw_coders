"""Auto-trade condition request/response schemas."""
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class AutoTradeAction(str, Enum):
    """Action to take when a condition triggers."""

    BUY = "BUY"
    SELL = "SELL"


class ConditionOperator(str, Enum):
    """Comparison operator applied to the observed stock price."""

    LT = "<"
    LTE = "<="
    GT = ">"
    GTE = ">="
    EQ = "="


class AutoTradeStatus(str, Enum):
    """Lifecycle status of an auto-trade condition."""

    ACTIVE = "active"
    TRIGGERED = "triggered"
    CANCELLED = "cancelled"


class AutoTradeConditionCreate(BaseModel):
    """Payload to create a new auto-buy/auto-sell condition."""

    stock_id: int
    action: AutoTradeAction
    operator: ConditionOperator
    threshold_price: Decimal
    quantity: Decimal


class AutoTradeConditionUpdate(BaseModel):
    """Patch payload for an existing condition; all fields optional."""

    action: Optional[AutoTradeAction] = None
    operator: Optional[ConditionOperator] = None
    threshold_price: Optional[Decimal] = None
    quantity: Optional[Decimal] = None


class AutoTradeCondition(BaseModel):
    """A single auto-trade condition."""

    condition_id: int
    portfolio_id: int
    stock_id: int
    symbol: Optional[str] = None
    short_name: Optional[str] = None
    user_id: int
    action: AutoTradeAction
    operator: ConditionOperator
    threshold_price: Decimal
    quantity: Decimal
    status: AutoTradeStatus
    last_checked_at: Optional[datetime] = None
    last_error: Optional[str] = None
    triggered_at: Optional[datetime] = None
    trans_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AutoTradeConditionListResponse(BaseModel):
    """A portfolio's auto-trade conditions."""

    conditions: list[AutoTradeCondition]


class AutoTradeCheckResult(BaseModel):
    """Outcome of running an auto-trade check."""

    conditions_checked: int
    triggered: int
    failed: int
    checked_at: datetime
