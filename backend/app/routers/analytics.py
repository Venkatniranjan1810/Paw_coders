"""P&L analytics API routes."""
from decimal import Decimal
from typing import Annotated, Literal

import pandas as pd
from app.exceptions import NotFoundError
from app.models import analytics as analytics_model
from app.models import portfolio as portfolio_model
from app.models import stock as stock_model
from app.routers.utils import require_portfolio_exists
from app.schemas.analytics import (
    AllocationInsight,
    PerformersResponse,
    PortfolioPnl,
    PortfoliosRiskResponse,
    StockPnl,
)
from app.services import analytics as analytics_service
from app.services import market_data
from fastapi import APIRouter, Query

PERFORMER_METRICS = Literal["total_pnl_pct", "total_pnl", "unrealized_pnl_pct"]

router = APIRouter(tags=["Analytics"])


def _enrich_live(holdings: list[dict]) -> list[dict]:
    """Overwrite each holding's price_live/market_value with a live quote."""
    for holding in holdings:
        symbol = holding.get("symbol")
        live = market_data.get_live_price(symbol) if symbol else None
        if live is None:
            continue
        quantity = holding.get("quantity")
        holding["price_live"] = live
        holding["market_value"] = Decimal(quantity) * live if quantity is not None else None
    return holdings


@router.get(
    "/stocks/{stock_id}/pnl",
    response_model=StockPnl,
    summary="Profit & loss for a single stock",
)
def get_stock_pnl(stock_id: int):
    """Unrealized + realized P&L for a stock, aggregated over every holding."""
    stock = stock_model.get_stock_by_id(stock_id)
    if stock is None:
        raise NotFoundError(f"Stock {stock_id} not found")

    holdings = _enrich_live(analytics_model.get_holdings_by_stock(stock_id))
    transactions = analytics_model.get_transactions_by_stock(stock_id)
    return analytics_service.build_stock_pnl(stock, holdings, transactions)


@router.get(
    "/portfolios/{portfolio_id}/pnl",
    response_model=PortfolioPnl,
    summary="Portfolio profit & loss with a per-holding breakdown",
)
@require_portfolio_exists
def get_portfolio_pnl(portfolio_id: int):
    """Sum of unrealized and realized P&L across a portfolio's stock holdings."""

    holdings = _enrich_live(analytics_model.get_portfolio_holdings(portfolio_id))
    transactions = analytics_model.get_transactions_all(portfolio_id)
    return analytics_service.build_portfolio_pnl(portfolio_id, holdings, transactions)


@router.get(
    "/portfolios/performers",
    response_model=PerformersResponse,
    summary="Top & worst current holding for each of a user's portfolios",
)
def get_portfolios_performers(
    user_id: Annotated[int, Query(alias="userId")],
    metric: PERFORMER_METRICS = "total_pnl_pct",
):
    """Rank each portfolio's current holdings by a P&L metric and return the best and worst."""
    performers: list[dict] = []
    for portfolio in portfolio_model.get_portfolios_by_user(user_id):
        portfolio_id = portfolio["portfolio_id"]
        holdings = _enrich_live(analytics_model.get_portfolio_holdings(portfolio_id))
        transactions = analytics_model.get_transactions_all(portfolio_id)
        pnl = analytics_service.build_portfolio_pnl(portfolio_id, holdings, transactions)
        ranking = analytics_service.select_performers(pnl["holdings"], metric)
        performers.append(
            {
                "portfolio_id": portfolio_id,
                "name": portfolio.get("name"),
                "holdings_count": ranking["holdings_count"],
                "metric": ranking["metric"],
                "top_performer": ranking["top_performer"],
                "worst_performer": ranking["worst_performer"],
            }
        )
    return {"portfolios": performers}


@router.get(
    "/portfolios/risk",
    response_model=PortfoliosRiskResponse,
    summary="Risk metrics for each of a user's portfolios",
)
def get_portfolios_risk(
    user_id: Annotated[int, Query(alias="userId")],
    lookback_days: Annotated[int, Query(alias="lookbackDays", ge=30, le=2520)] = 252,
    risk_free_rate: Annotated[float, Query(alias="riskFreeRate")] = 0.0,
    benchmark_symbol: Annotated[str, Query(alias="benchmarkSymbol")] = "SPY",
):
    """Volatility, Sharpe, drawdown, VaR and beta for every portfolio's current holdings."""
    benchmark_stock = stock_model.get_stock_by_symbol(benchmark_symbol)
    benchmark_close = (
        stock_model.get_close_series(benchmark_stock["stock_id"])
        if benchmark_stock is not None
        else pd.Series(dtype="float64")
    )

    results: list[dict] = []
    for portfolio in portfolio_model.get_portfolios_by_user(user_id):
        portfolio_id = portfolio["portfolio_id"]
        holdings = analytics_model.get_portfolio_holdings(portfolio_id)
        adj_closes, closes = analytics_model.get_portfolio_price_frames(portfolio_id)
        risk = analytics_service.build_portfolio_risk(
            portfolio_id,
            holdings,
            adj_closes,
            closes,
            benchmark_close=benchmark_close,
            benchmark_symbol=benchmark_symbol,
            lookback_days=lookback_days,
            risk_free_rate=risk_free_rate,
        )
        results.append({"name": portfolio.get("name"), **risk})
    return {"portfolios": results}


@router.get(
    "/portfolios/{portfolio_id}/allocation/by-quote-type",
    response_model=AllocationInsight,
    summary="Portfolio allocation by quote_type (for a pie chart)",
)
@require_portfolio_exists
def get_allocation_by_quote_type(portfolio_id: int):
    """Count holdings grouped by their stock's quote_type (EQUITY, ETF, ...)."""
    return _allocation(portfolio_id, "quote_type")


@router.get(
    "/portfolios/{portfolio_id}/allocation/by-sector",
    response_model=AllocationInsight,
    summary="Portfolio allocation by sector (for a pie chart)",
)
@require_portfolio_exists
def get_allocation_by_sector(portfolio_id: int):
    """Count holdings grouped by their stock's sector."""
    return _allocation(portfolio_id, "sector")


def _allocation(portfolio_id: int, grouping_key: str) -> dict:
    """Build the allocation payload for a grouping key."""
    rows = analytics_model.get_portfolio_allocation_rows(portfolio_id)
    return analytics_service.build_allocation(portfolio_id, rows, grouping_key)
