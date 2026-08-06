"""Watchlist API routes."""
from typing import Annotated, Optional

from app.exceptions import InternalError, NotFoundError
from app.models import stock as stock_model
from app.models import watchlist as watchlist_model
from app.schemas.watchlist import WatchlistAddRequest, WatchlistItem
from fastapi import APIRouter, status

router = APIRouter(prefix="/watchlist", tags=["Watchlist"])


@router.get("", response_model=list[WatchlistItem], summary="List all stocks in the single watchlist")
def list_watchlist():
    """Return the shared watchlist with latest price change details."""
    return watchlist_model.get_watchlist_stocks()


@router.post("", response_model=WatchlistItem, status_code=status.HTTP_201_CREATED, summary="Add a stock to the watchlist by symbol")
def add_watchlist_item(payload: WatchlistAddRequest):
    """Add a stock to the shared watchlist using its symbol."""
    stock = stock_model.get_stock_by_symbol(payload.symbol)
    if stock is None:
        raise NotFoundError(f"Stock symbol '{payload.symbol}' not found")

    watchlist_model.add_to_watchlist(stock["stock_id"])
    item = watchlist_model.get_watchlist_item(stock["stock_id"])
    if item is None:
        raise InternalError("Failed to load the newly added watchlist item")
    return item


@router.post(
    "/{stock_id}",
    response_model=WatchlistItem,
    status_code=status.HTTP_201_CREATED,
    summary="Add a stock to the watchlist by stock ID",
)
def add_watchlist_stock_id(stock_id: int):
    """Add a stock to the shared watchlist using its stock ID."""
    stock = stock_model.get_stock_by_id(stock_id)
    if stock is None:
        raise NotFoundError(f"Stock {stock_id} not found")

    watchlist_model.add_to_watchlist(stock_id)
    item = watchlist_model.get_watchlist_item(stock_id)
    if item is None:
        raise InternalError("Failed to load the newly added watchlist item")
    return item


@router.delete(
    "/{stock_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a stock from the watchlist",
)
def remove_watchlist_stock(stock_id: int):
    """Remove a stock from the shared watchlist."""
    if not watchlist_model.remove_from_watchlist(stock_id):
        raise NotFoundError(f"Stock {stock_id} not found in watchlist")
    return None
