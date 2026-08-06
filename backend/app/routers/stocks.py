"""Stocks API routes."""
from datetime import date, datetime, timezone
from typing import Annotated, Optional

from app.exceptions import BadRequestError, NotFoundError
from app.models import stock as stock_model
from app.routers.utils import require_stock_exists
from app.schemas.stock import (
    CompareStockPricesResponse,
    PriceCandle,
    Quote,
    Stock,
    StockSummary,
)
from app.services import market_data
from fastapi import APIRouter, Query

router = APIRouter(prefix="/stocks", tags=["Stocks"])


@router.get("", response_model=list[StockSummary], summary="List known stocks (name and/or symbol)")
def list_stocks(
    search: Annotated[Optional[str], Query(description="Filter by symbol or name substring.")] = None,
    sector: Annotated[Optional[str], Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """Return a filtered, paged list of stocks."""
    return stock_model.get_stocks(search=search, sector=sector, limit=limit, offset=offset)


@router.get(
    "/compare",
    response_model=CompareStockPricesResponse,
    summary="Compare OHLC candles for two stocks",
)
def compare_stock_prices(
    stock_id_a: int = Query(..., alias="stockIdA", description="First stock id."),
    stock_id_b: int = Query(..., alias="stockIdB", description="Second stock id."),
    interval: Annotated[str, Query(description="Chart interval (1d, 1w, 1mo, 1y)." )] = "1d",
    range_name: Annotated[Optional[str], Query(alias="range", description="Bank-style period (last_day, last_week, last_month, last_6_months, last_1_year, last_5_years, custom)." )] = None,
    start_date: Annotated[Optional[date], Query(alias="startDate", description="Inclusive start date for custom ranges.")] = None,
    end_date: Annotated[Optional[date], Query(alias="endDate", description="Inclusive end date for custom ranges.")] = None,
    start: Annotated[Optional[datetime], Query(description="Inclusive start timestamp.")] = None,
    end: Annotated[Optional[datetime], Query(description="Inclusive end timestamp.")] = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 500,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """Return OHLC candles for two stocks so the UI can plot them together."""
    first_stock = stock_model.get_stock_by_id(stock_id_a)
    if first_stock is None:
        raise NotFoundError(f"Stock {stock_id_a} not found")

    second_stock = stock_model.get_stock_by_id(stock_id_b)
    if second_stock is None:
        raise NotFoundError(f"Stock {stock_id_b} not found")

    selected_range = (range_name or "").strip().lower()
    if selected_range == "custom" and (start_date is None or end_date is None):
        raise BadRequestError("Custom ranges require both startDate and endDate")

    if start is None and end is None:
        if start_date is None and end_date is None and selected_range not in {None, "", "all", "custom"}:
            start_date, end_date = stock_model.resolve_time_range(selected_range)

        if start_date is not None:
            start = datetime.combine(start_date, datetime.min.time())
        if end_date is not None:
            end = datetime.combine(end_date, datetime.max.time())

    if start is not None and end is not None and start > end:
        raise BadRequestError("start must be on or before end")

    first_candles = stock_model.get_stock_prices(
        stock_id_a,
        interval=interval,
        start=start,
        end=end,
        limit=limit,
        offset=offset,
    )
    second_candles = stock_model.get_stock_prices(
        stock_id_b,
        interval=interval,
        start=start,
        end=end,
        limit=limit,
        offset=offset,
    )

    return stock_model.build_compare_price_payload(
        first_stock_id=stock_id_a,
        first_symbol=first_stock["symbol"],
        first_candles=first_candles,
        second_stock_id=stock_id_b,
        second_symbol=second_stock["symbol"],
        second_candles=second_candles,
        interval=interval,
        range_label=(range_name or "all").replace("_", " ").title() if range_name not in {None, "", "all"} else None,
    )


@router.get("/quotes", response_model=list[Quote], summary="Live quotes for a set of stocks")
def get_stock_quotes(
    ids: Annotated[Optional[str], Query(description="Comma-separated stock ids. Omit to quote all stocks.")] = None,
):
    """Return the current live price for each requested stock.

    Accepts multiple stock ids in a single call so the UI can refresh a whole
    list of live prices in one request (used by the Stocks-tab minute refresh).
    """
    if ids:
        stock_ids = [int(token) for token in ids.split(",") if token.strip().isdigit()]
    else:
        stock_ids = [row["stock_id"] for row in stock_model.get_stocks(limit=500)]

    rows: list[dict] = []
    for stock_id in stock_ids:
        quote = stock_model.get_latest_quote(stock_id)
        if quote is not None:
            rows.append(quote)

    if not rows:
        return []

    live = market_data.get_live_prices([row["symbol"] for row in rows])
    now = datetime.now(timezone.utc)
    for row in rows:
        live_price = live.get(row["symbol"].upper())
        if live_price is not None:
            row["price"] = live_price
            row["ts"] = now
    return rows


@router.get("/{stock_id}", response_model=Stock, summary="Get full stock detail")
@require_stock_exists
def get_stock(stock_id: int):
    """Return full stock detail by id, with a live current price when available."""
    row = stock_model.get_stock_by_id(stock_id)

    live = market_data.get_live_price(row["symbol"])
    if live is not None:
        row["current_price"] = live
        row["day_change"], row["day_change_pct"] = stock_model.compute_day_change(
            live, row.get("previous_close")
        )
    return row


@router.get(
    "/{stock_id}/prices",
    response_model=list[PriceCandle],
    summary="Price history (OHLC candles) for a stock",
)
def get_stock_prices(
    stock_id: int,
    interval: Annotated[str, Query(description="Chart interval (1d, 1w, 1mo, 1y).")] = "1d",
    range_name: Annotated[Optional[str], Query(alias="range", description="Bank-style period (last_day, last_week, last_month, last_6_months, last_1_year, last_5_years, custom)." )] = None,
    start_date: Annotated[Optional[date], Query(alias="startDate", description="Inclusive start date for custom ranges.")] = None,
    end_date: Annotated[Optional[date], Query(alias="endDate", description="Inclusive end date for custom ranges.")] = None,
    start: Annotated[Optional[datetime], Query(description="Inclusive start timestamp.")] = None,
    end: Annotated[Optional[datetime], Query(description="Inclusive end timestamp.")] = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 500,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """Return candles aggregated to the requested chart interval and time frame."""
    selected_range = (range_name or "").strip().lower()
    if selected_range == "custom" and (start_date is None or end_date is None):
        raise BadRequestError("Custom ranges require both startDate and endDate")

    if start is None and end is None:
        if start_date is None and end_date is None and selected_range not in {None, "", "all", "custom"}:
            start_date, end_date = stock_model.resolve_time_range(selected_range)

        if start_date is not None:
            start = datetime.combine(start_date, datetime.min.time())
        if end_date is not None:
            end = datetime.combine(end_date, datetime.max.time())

    if start is not None and end is not None and start > end:
        raise BadRequestError("start must be on or before end")

    return stock_model.get_stock_prices(
        stock_id,
        interval=interval,
        start=start,
        end=end,
        limit=limit,
        offset=offset,
    )


@router.get("/{stock_id}/quote", response_model=Quote, summary="Latest live price for a stock")
@require_stock_exists
def get_stock_quote(stock_id: int):
    """Return the current live price, falling back to the last DB close."""
    row = stock_model.get_latest_quote(stock_id)
    if row is None:
        raise NotFoundError(f"No price data for stock {stock_id}")

    live = market_data.get_live_price(row["symbol"])
    if live is not None:
        row["price"] = live
        row["ts"] = datetime.now(timezone.utc)
    return row
