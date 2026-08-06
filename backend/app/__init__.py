"""Application factory and router registration."""
import asyncio
import logging
from contextlib import asynccontextmanager

from app.config import settings
from app.handlers import configure_logging, register_exception_handlers
from app.routers import (
    alerts,
    analytics,
    auto_trade,
    holdings,
    portfolios,
    stocks,
    transactions,
    users,
    watchlist,
)
from app.services.alerts import run_alert_check_for_all_users
from app.services.price_refresh import refresh_all_prices
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

API_PREFIX = "/api/v1"


async def _run_periodic_refresh() -> None:
    """Background loop refreshing stock_prices every PRICE_REFRESH_INTERVAL_SECONDS."""
    while True:
        await asyncio.sleep(settings.PRICE_REFRESH_INTERVAL_SECONDS)
        try:
            await asyncio.to_thread(refresh_all_prices)
        except Exception:
            logging.exception("Periodic price refresh failed")


async def _run_periodic_alert_check() -> None:
    """Background loop evaluating risk/health alerts every ALERT_CHECK_INTERVAL_SECONDS."""
    while True:
        await asyncio.sleep(settings.ALERT_CHECK_INTERVAL_SECONDS)
        try:
            await asyncio.to_thread(run_alert_check_for_all_users)
        except Exception:
            logging.exception("Periodic alert check failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start/stop the periodic refresh and alert-check tasks with the app."""
    refresh_task = asyncio.create_task(_run_periodic_refresh())
    alert_task = asyncio.create_task(_run_periodic_alert_check())
    try:
        yield
    finally:
        for task in (refresh_task, alert_task):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    configure_logging()

    app = FastAPI(
        title="Quantitative Portfolio Management System (QPMS) API",
        version="1.0.0",
        description="REST API for the Quantitative Portfolio Management System.",
        lifespan=lifespan,
    )

    # CORS — allow the Streamlit frontend to call the API.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Centralized exception handling: domain errors, validation failures,
    # MySQL outages and unexpected exceptions all return a consistent JSON
    # envelope (see app/handlers.py).
    register_exception_handlers(app)

    # Register routers here. Add new modules (analytics, factors, ...) below.
    # analytics is registered before portfolios so the static path
    # /portfolios/performers is matched before /portfolios/{portfolio_id}.
    app.include_router(users.router, prefix=API_PREFIX)
    app.include_router(stocks.router, prefix=API_PREFIX)
    app.include_router(analytics.router, prefix=API_PREFIX)
    app.include_router(portfolios.router, prefix=API_PREFIX)
    app.include_router(holdings.router, prefix=API_PREFIX)
    app.include_router(transactions.router, prefix=API_PREFIX)
    app.include_router(watchlist.router, prefix=API_PREFIX)
    app.include_router(alerts.router, prefix=API_PREFIX)
    app.include_router(auto_trade.router, prefix=API_PREFIX)

    @app.get("/health", tags=["Meta"])
    def health() -> dict:
        return {"status": "ok"}

    return app
