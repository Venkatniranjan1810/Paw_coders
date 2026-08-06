"""Holdings API routes (browse / buy / sell)."""
from decimal import Decimal
from typing import Annotated, Optional

from app.exceptions import BadRequestError, NotFoundError
from app.models import holding as holding_model
from app.models import stock as stock_model
from app.routers.utils import require_portfolio_exists
from app.schemas.holding import Holding, HoldingBuy
from app.schemas.transaction import Transaction
from app.services import market_data
from fastapi import APIRouter, Query, status

router = APIRouter(prefix="/portfolios/{portfolio_id}/holdings", tags=["Holdings"])


def _latest_price(stock_id: int, symbol: Optional[str] = None) -> Optional[Decimal]:
    """Return a live Yahoo Finance price, falling back to the last DB close."""
    if symbol:
        live = market_data.get_live_price(symbol)
        if live is not None:
            return live
    quote = stock_model.get_latest_quote(stock_id)
    return Decimal(quote["price"]) if quote else None


def _enrich_live(holding: dict) -> dict:
    """Overwrite price_live/market_value with a live quote, when available."""
    live = market_data.get_live_price(holding["symbol"])
    if live is not None:
        holding["price_live"] = live
        holding["market_value"] = Decimal(holding["quantity"]) * live
    return holding


@router.get("", response_model=list[Holding], summary="Browse portfolio holdings (with live value)")
@require_portfolio_exists
def list_holdings(portfolio_id: int):
    """Return the current positions for a portfolio."""
    return [_enrich_live(row) for row in holding_model.get_holdings(portfolio_id)]


@router.post(
    "",
    response_model=Holding,
    status_code=status.HTTP_201_CREATED,
    summary="Add / buy a stock into the portfolio",
)
@require_portfolio_exists
def add_holding(portfolio_id: int, payload: HoldingBuy):
    """Buy a stock: debit cash, upsert holding, record a BUY transaction."""

    stock = stock_model.get_stock_by_symbol(payload.symbol)
    if stock is None:
        raise BadRequestError(f"Unknown stock symbol '{payload.symbol}'")

    price = payload.price or _latest_price(stock["stock_id"], stock["symbol"])
    if price is None:
        raise BadRequestError("No live price available for purchase")

    try:
        return _enrich_live(holding_model.buy_stock(portfolio_id, stock["stock_id"], payload.quantity, price))
    except holding_model.InsufficientFundsError as exc:
        raise BadRequestError(str(exc)) from exc
    except ValueError as exc:
        raise BadRequestError(str(exc)) from exc


@router.delete(
    "/{stock_id}",
    response_model=Transaction,
    summary="Remove / sell a stock from the portfolio",
)
@require_portfolio_exists
def sell_holding(
    portfolio_id: int,
    stock_id: int,
    quantity: Annotated[Optional[int], Query(gt=0, description="Whole shares to sell. Omit to sell all.")] = None,
    price: Annotated[Optional[Decimal], Query(gt=0, description="Sell price per unit. Defaults to live price.")] = None,
):
    """Sell part or all of a position: credit cash, record a SELL transaction."""

    sell_price = price
    if sell_price is None:
        stock = stock_model.get_stock_by_id(stock_id)
        sell_price = _latest_price(stock_id, stock["symbol"] if stock else None)
    if sell_price is None:
        raise BadRequestError("No price provided and no live price available")

    try:
        return holding_model.sell_stock(portfolio_id, stock_id, sell_price, quantity)
    except holding_model.InsufficientQuantityError as exc:
        raise NotFoundError(str(exc)) from exc
    except ValueError as exc:
        raise BadRequestError(str(exc)) from exc
