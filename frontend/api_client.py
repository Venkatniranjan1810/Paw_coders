"""Thin HTTP client for the QPMS FastAPI backend.

One method per endpoint actually registered in ``backend/app/__init__.py``.
Every method raises ``APIError`` on network failure or a non-2xx response so
callers only ever need to catch one exception type.
"""
import os
from typing import Any, Optional

import httpx

DEFAULT_BASE_URL = "http://127.0.0.1:8001"


class APIError(RuntimeError):
    """Raised when the backend cannot be reached or returns an error."""


class ApiClient:
    def __init__(self, base_url: Optional[str] = None) -> None:
        self.base_url = (base_url or os.getenv("API_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")
        self.client = httpx.Client(base_url=self.base_url, timeout=10.0)

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "ApiClient":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = self.client.request(method, path, **kwargs)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            try:
                detail = exc.response.json().get("detail", exc.response.text)
            except ValueError:
                detail = exc.response.text or str(exc)
            raise APIError(str(detail)) from exc
        except httpx.RequestError as exc:
            raise APIError(f"Unable to reach backend at {self.base_url}: {exc}") from exc

        if not response.content:
            return None
        return response.json()

    def _request_bytes(self, method: str, path: str, **kwargs: Any) -> bytes:
        """Like _request but returns raw bytes (for downloads)."""
        try:
            response = self.client.request(method, path, **kwargs)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            try:
                detail = exc.response.json().get("detail", exc.response.text)
            except ValueError:
                detail = exc.response.text or str(exc)
            raise APIError(str(detail)) from exc
        except httpx.RequestError as exc:
            raise APIError(f"Unable to reach backend at {self.base_url}: {exc}") from exc
        return response.content

    # --- Meta ---------------------------------------------------------

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    # --- Users ----------------------------------------------------------

    def list_users(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/v1/users")

    def get_user(self, user_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/users/{user_id}")

    # --- Portfolios -------------------------------------------------------

    def list_portfolios(self, user_id: int) -> list[dict[str, Any]]:
        return self._request("GET", "/api/v1/portfolios", params={"userId": user_id})

    def get_portfolio(self, portfolio_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/portfolios/{portfolio_id}")

    def create_portfolio(self, user_id: int, name: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/v1/portfolios",
            json={"user_id": user_id, "name": name},
        )

    def delete_portfolio(self, portfolio_id: int) -> None:
        self._request("DELETE", f"/api/v1/portfolios/{portfolio_id}")

    # --- Holdings ---------------------------------------------------------

    def list_holdings(self, portfolio_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/v1/portfolios/{portfolio_id}/holdings")

    def buy_stock(
        self, portfolio_id: int, symbol: str, quantity: int, price: Optional[float] = None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"symbol": symbol, "quantity": quantity}
        if price is not None and price > 0:
            payload["price"] = price
        return self._request("POST", f"/api/v1/portfolios/{portfolio_id}/holdings", json=payload)

    def sell_stock(
        self,
        portfolio_id: int,
        stock_id: int,
        quantity: Optional[int] = None,
        price: Optional[float] = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if quantity is not None:
            params["quantity"] = quantity
        if price is not None and price > 0:
            params["price"] = price
        return self._request(
            "DELETE", f"/api/v1/portfolios/{portfolio_id}/holdings/{stock_id}", params=params
        )

    # --- Stocks -------------------------------------------------------

    def list_stocks(
        self,
        search: Optional[str] = None,
        sector: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if search:
            params["search"] = search
        if sector:
            params["sector"] = sector
        return self._request("GET", "/api/v1/stocks", params=params)

    def get_stock(self, stock_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/stocks/{stock_id}")

    def get_stock_prices(
        self,
        stock_id: int,
        interval: str = "1d",
        start: Optional[str] = None,
        end: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"interval": interval}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        if limit:
            params["limit"] = limit
        return self._request(
            "GET", f"/api/v1/stocks/{stock_id}/prices", params=params
        )

    def get_stock_quote(self, stock_id: int) -> Optional[dict[str, Any]]:
        try:
            return self._request("GET", f"/api/v1/stocks/{stock_id}/quote")
        except APIError:
            return None

    def get_stock_quotes(self, stock_ids: list[int]) -> list[dict[str, Any]]:
        """Fetch live quotes for many stocks in a single request."""
        if not stock_ids:
            return []
        ids = ",".join(str(int(i)) for i in stock_ids)
        try:
            return self._request("GET", "/api/v1/stocks/quotes", params={"ids": ids})
        except APIError:
            return []

    def compare_stock_prices(
        self,
        stock_id_a: int,
        stock_id_b: int,
        interval: str = "1d",
        range_name: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 500,
    ) -> dict[str, Any]:
        """OHLC candle series for two stocks compared side by side."""
        params: dict[str, Any] = {
            "stockIdA": stock_id_a,
            "stockIdB": stock_id_b,
            "interval": interval,
            "limit": limit,
        }
        if range_name:
            params["range"] = range_name
        if start_date:
            params["startDate"] = start_date
        if end_date:
            params["endDate"] = end_date
        return self._request("GET", "/api/v1/stocks/compare", params=params)

    # --- Analytics ------------------------------------------------------

    def get_stock_pnl(self, stock_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/stocks/{stock_id}/pnl")

    def get_portfolio_pnl(self, portfolio_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/portfolios/{portfolio_id}/pnl")

    def get_portfolios_performers(
        self, user_id: int, metric: str = "total_pnl_pct"
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            "/api/v1/portfolios/performers",
            params={"userId": user_id, "metric": metric},
        )

    def get_portfolios_risk(
        self,
        user_id: int,
        lookback_days: int = 252,
        risk_free_rate: float = 0.0,
        benchmark_symbol: str = "SPY",
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            "/api/v1/portfolios/risk",
            params={
                "userId": user_id,
                "lookbackDays": lookback_days,
                "riskFreeRate": risk_free_rate,
                "benchmarkSymbol": benchmark_symbol,
            },
        )

    def get_allocation(self, portfolio_id: int, by: str = "sector") -> dict[str, Any]:
        """Allocation pie data grouped by 'sector' or 'quote-type'."""
        return self._request(
            "GET", f"/api/v1/portfolios/{portfolio_id}/allocation/by-{by}"
        )

    # --- Transactions -------------------------------------------------------

    def list_transactions(
        self,
        portfolio_id: int,
        trans_type: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        if "limit" in kwargs:
            limit = kwargs.pop("limit")
        if "offset" in kwargs:
            offset = kwargs.pop("offset")
        if kwargs:
            unexpected = ", ".join(sorted(kwargs.keys()))
            raise TypeError(f"Unexpected keyword argument(s): {unexpected}")

        params: dict[str, Any] = {"limit": 100 if limit is None else limit, "offset": 0 if offset is None else offset}
        if trans_type:
            params["transType"] = trans_type
        return self._request(
            "GET", f"/api/v1/portfolios/{portfolio_id}/transactions", params=params
        )

    def list_transactions_history(
        self,
        portfolio_id: int,
        range_name: Optional[str] = None,
        interval: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        trans_type: Optional[str] = None,
        limit: int = 200,
    ) -> dict[str, Any]:
        """Transaction history for a bank-style period or custom date range."""
        params: dict[str, Any] = {"limit": limit}
        if interval:
            params["interval"] = interval
        if range_name:
            params["range"] = range_name
        if start_date:
            params["startDate"] = start_date
        if end_date:
            params["endDate"] = end_date
        if trans_type:
            params["transType"] = trans_type
        return self._request(
            "GET", f"/api/v1/portfolios/{portfolio_id}/transactions/history", params=params
        )

    def download_transactions_report(
        self,
        portfolio_id: int,
        range_name: Optional[str] = None,
        interval: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        trans_type: Optional[str] = None,
    ) -> bytes:
        """Download a PDF report of the selected transaction history."""
        params: dict[str, Any] = {}
        if interval:
            params["interval"] = interval
        if range_name:
            params["range"] = range_name
        if start_date:
            params["startDate"] = start_date
        if end_date:
            params["endDate"] = end_date
        if trans_type:
            params["transType"] = trans_type
        return self._request_bytes(
            "GET", f"/api/v1/portfolios/{portfolio_id}/transactions/report", params=params
        )

    # --- Watchlist ----------------------------------------------------------

    def list_watchlist(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/v1/watchlist")

    def add_to_watchlist(self, symbol: str) -> dict[str, Any]:
        return self._request("POST", "/api/v1/watchlist", json={"symbol": symbol})

    def add_stock_to_watchlist(self, stock_id: int) -> dict[str, Any]:
        return self._request("POST", f"/api/v1/watchlist/{stock_id}")

    def remove_from_watchlist(self, stock_id: int) -> None:
        self._request("DELETE", f"/api/v1/watchlist/{stock_id}")

    # --- Alerts ------------------------------------------------------------

    def list_alerts(
        self,
        user_id: int,
        portfolio_id: Optional[int] = None,
        unread_only: bool = False,
        limit: int = 200,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"userId": user_id, "unreadOnly": unread_only, "limit": limit}
        if portfolio_id is not None:
            params["portfolioId"] = portfolio_id
        return self._request("GET", "/api/v1/alerts", params=params)

    def run_alert_check(self, user_id: int, send_email: bool = False) -> dict[str, Any]:
        return self._request(
            "POST", "/api/v1/alerts/check", params={"userId": user_id, "sendEmail": send_email}
        )

    def mark_alert_read(self, alert_id: int) -> dict[str, Any]:
        return self._request("POST", f"/api/v1/alerts/{alert_id}/read")
