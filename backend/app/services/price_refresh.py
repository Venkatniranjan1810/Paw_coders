"""Orchestrates periodic/live refresh of the stock_prices table.

Fetches today's live quote for every tracked symbol (in parallel) and
overrides the current day's daily candle via an upsert, so the table always
reflects live prices.
"""
import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import asynccontextmanager
from datetime import date, datetime, time, timezone

from decimal import Decimal

from app.config import settings
from app.models import stock as stock_model
from app.services import auto_trade as auto_trade_service
from app.services.market_data import fetch_live_quote
from fastapi import FastAPI

_QUOTE_FETCH_WORKERS = 8
_refresh_lock = threading.Lock()


def refresh_all_prices() -> dict:
    """Fetch live quotes for all stocks and upsert today's candles.

    Returns a summary dict. A second concurrent call returns immediately with
    status "in_progress" instead of running again.
    """
    if not _refresh_lock.acquire(blocking=False):
        return {"status": "in_progress"}

    try:
        symbols = stock_model.get_all_symbols()
        if not symbols:
            return {"status": "ok", "total": 0, "updated": 0, "failed": 0,
                    "refreshed_at": datetime.now(timezone.utc).isoformat()}

        quotes: dict[int, dict] = {}
        failed = 0
        with ThreadPoolExecutor(max_workers=_QUOTE_FETCH_WORKERS) as pool:
            futures = {pool.submit(fetch_live_quote, symbol["symbol"]): symbol for symbol in symbols}
            for future in as_completed(futures):
                symbol = futures[future]
                quote = future.result()
                if quote is None:
                    failed += 1
                    logging.warning("No live quote for %s", symbol["symbol"])
                else:
                    quotes[symbol["stock_id"]] = quote

        today_midnight = datetime.combine(date.today(), time.min)
        rows = [
            (stock_id, today_midnight, "1d", quote["open"], quote["high"],
             quote["low"], quote["close"], quote["close"], quote["volume"])
            for stock_id, quote in quotes.items()
        ]
        stock_model.upsert_live_prices(rows)

        try:
            prices = {stock_id: Decimal(str(quote["close"])) for stock_id, quote in quotes.items()}
            auto_trade_service.run_auto_trade_check_for_all_active(prices)
        except Exception:
            logging.exception("Auto-trade condition check failed after price refresh")

        return {
            "status": "ok",
            "total": len(symbols),
            "updated": len(rows),
            "failed": failed,
            "refreshed_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        logging.exception("Price refresh failed: %s", exc)
        return {"status": "error", "error": str(exc)}
    finally:
        _refresh_lock.release()


async def _run_periodic_refresh() -> None:
    """Background loop refreshing stock_prices every PRICE_REFRESH_INTERVAL_SECONDS."""
    while True:
        await asyncio.sleep(settings.PRICE_REFRESH_INTERVAL_SECONDS)
        try:
            await asyncio.to_thread(refresh_all_prices)
        except Exception:
            logging.exception("Periodic price refresh failed")


@asynccontextmanager
async def lifespan_refresh(app: FastAPI):
    """Start/stop the periodic stock_prices refresh task."""
    task = asyncio.create_task(_run_periodic_refresh())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
