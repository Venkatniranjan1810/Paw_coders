"""Shared helpers used across the app's page modules: formatting, price
helpers, the live ticker, dialogs, the manual alert-check trigger and the
per-page app scaffolding (state, sidebar, shared data loading)."""
import os
from typing import Any, Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import api_client
import utils
from api_client import APIError, ApiClient
from theme import CHART_COLORS, PLOTLY_LAYOUT, inject_css, spark_svg, ticker_html

DEFAULT_BASE_URL = getattr(api_client, "DEFAULT_BASE_URL", "http://127.0.0.1:8001")


class AppContext:
    """Shared data loaded once per run and handed to every page."""

    def __init__(
        self,
        client,
        selected_user_id: int,
        selected_portfolio_id: int,
        user,
        portfolio,
        metrics: dict[str, float],
        holdings_df,
    ) -> None:
        self.client = client
        self.selected_user_id = selected_user_id
        self.selected_portfolio_id = selected_portfolio_id
        self.user = user
        self.portfolio = portfolio
        self.metrics = metrics
        self.holdings_df = holdings_df


# --- App scaffolding -------------------------------------------------------

def initialize_state() -> None:
    st.session_state.setdefault("api_base_url", os.getenv("API_BASE_URL", DEFAULT_BASE_URL))
    st.session_state.setdefault("selected_user_id", None)
    st.session_state.setdefault("selected_portfolio_id", None)
    st.session_state.setdefault("trade_basket", [])
    st.session_state.setdefault("pending_order", None)
    st.session_state.setdefault("trade_flash", None)
    st.session_state.setdefault("alerts_popup_shown", False)
    st.session_state.setdefault("open_alerts_dialog", False)
    st.session_state.setdefault("trade_mode", "buy")


def get_client() -> ApiClient:
    return ApiClient(st.session_state.api_base_url)


def setup_app(page_title: str = "Portfolio Quant Dashboard") -> ApiClient:
    """Entrypoint bootstrap: page config, CSS, state, client and backend check."""
    st.set_page_config(
        page_title=page_title,
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_css()
    initialize_state()
    client = get_client()
    try:
        client.health()
    except APIError as exc:
        st.error(str(exc))
        st.info("Start the backend with: uvicorn main:app --reload  (run from the backend/ folder)")
        st.stop()
    return client


def _resolve_selected_context(client) -> None:
    """Pick a default user and portfolio for the current session when controls are hidden."""
    try:
        users = client.list_users()
    except APIError:
        users = []

    preferred_user = None
    for user in users:
        raw_name = str(user.get("user_name") or "").strip()
        if raw_name.lower().replace(" ", "") == "pawcoder":
            preferred_user = user
            break
    if preferred_user is None and users:
        preferred_user = users[0]

    if preferred_user is not None:
        st.session_state.selected_user_id = preferred_user["user_id"]
    else:
        st.session_state.selected_user_id = None
        st.session_state.selected_portfolio_id = None
        return

    try:
        portfolios = client.list_portfolios(int(st.session_state.selected_user_id))
    except APIError:
        portfolios = []

    portfolio_ids = [p["portfolio_id"] for p in portfolios]
    if portfolio_ids:
        if st.session_state.selected_portfolio_id not in portfolio_ids:
            st.session_state.selected_portfolio_id = portfolio_ids[0]
    else:
        st.session_state.selected_portfolio_id = None


def _render_sidebar(client, show_controls: bool = False) -> None:
    """Render the shared sidebar controls only on pages that opt in."""
    sidebar = st.sidebar

    _resolve_selected_context(client)

    if not show_controls:
        return

    sidebar.markdown(
        '<div class="sidebar-brand">Paw Coders<span>Quant Portfolio Suite</span></div>',
        unsafe_allow_html=True,
    )
    sidebar.header("Controls")
    sidebar.text_input("Backend URL", key="api_base_url")
    if sidebar.button("Refresh data", width="stretch"):
        st.rerun()

    sidebar.divider()

    try:
        users = client.list_users()
    except APIError:
        users = []

    if users:
        user_lookup = {int(user["user_id"]): user for user in users if user.get("user_id") is not None}
        user_ids = list(user_lookup.keys())
        if st.session_state.selected_user_id not in user_ids:
            st.session_state.selected_user_id = user_ids[0]
        selected_user_id = sidebar.selectbox(
            "User",
            options=user_ids,
            index=user_ids.index(int(st.session_state.selected_user_id)),
            format_func=lambda uid: str(user_lookup[uid].get("user_name") or f"User {uid}"),
            key="user_selector",
        )
        st.session_state.selected_user_id = int(selected_user_id)

        try:
            portfolios = client.list_portfolios(int(st.session_state.selected_user_id))
        except APIError:
            portfolios = []
        portfolio_ids = [p["portfolio_id"] for p in portfolios]
        portfolio_lookup = {p["portfolio_id"]: p for p in portfolios}
        if portfolio_ids:
            if st.session_state.selected_portfolio_id not in portfolio_ids:
                st.session_state.selected_portfolio_id = portfolio_ids[0]
            selected_portfolio_id = sidebar.selectbox(
                "Portfolio",
                options=portfolio_ids,
                index=portfolio_ids.index(st.session_state.selected_portfolio_id),
                format_func=lambda pid: portfolio_lookup[pid].get("name", f"Portfolio {pid}"),
                key="portfolio_selector",
            )
            st.session_state.selected_portfolio_id = selected_portfolio_id
        else:
            st.session_state.selected_portfolio_id = None
            sidebar.info("No portfolios yet for this user.")
    else:
        st.session_state.selected_user_id = None
        st.session_state.selected_portfolio_id = None
        sidebar.info("No users found in the database yet.")

    sidebar.caption("Create a new portfolio")
    portfolio_name = sidebar.text_input("Name", value="My Portfolio", key="new_portfolio_name")
    if sidebar.button("Create portfolio", use_container_width=True):
        if st.session_state.selected_user_id is not None:
            try:
                created_portfolio = client.create_portfolio(
                    int(st.session_state.selected_user_id), portfolio_name.strip() or "My Portfolio"
                )
                st.session_state.selected_portfolio_id = created_portfolio.get("portfolio_id")
                sidebar.success("Portfolio created")
                st.rerun()
            except APIError as exc:
                sidebar.error(str(exc))
        else:
            sidebar.error("Select a user before creating a portfolio.")


def _maybe_open_alerts_popup(client, selected_user_id: int) -> None:
    """Open the unread-alerts popup once per session when alerts exist."""
    try:
        _alert_payload = client.list_alerts(selected_user_id, unread_only=True, limit=50)
    except APIError:
        _alert_payload = {}

    if int(_alert_payload.get("unread_count") or 0) and not st.session_state.get("alerts_popup_shown"):
        st.session_state["alerts_popup_shown"] = True
        st.session_state["open_alerts_dialog"] = True

    if st.session_state.get("open_alerts_dialog"):
        alerts_dialog(client, selected_user_id)


def require_context(client: Optional[ApiClient] = None, show_controls: bool = False) -> AppContext:
    """Render the sidebar, load the shared data and return an AppContext.

    Stops the page when no user or portfolio exists yet. Every page calls this
    so navigation between pages keeps the same selected user/portfolio.
    """
    if client is None:
        client = get_client()
    _render_sidebar(client, show_controls=show_controls)

    if st.session_state.selected_user_id is None:
        st.info("No users exist yet — seed one via the backend/portfolio_db_setup scripts.")
        st.stop()
    if st.session_state.selected_portfolio_id is None:
        st.info("Create a portfolio in the sidebar to get started.")
        st.stop()

    selected_user_id = int(st.session_state.selected_user_id)
    selected_portfolio_id = int(st.session_state.selected_portfolio_id)

    user = client.get_user(selected_user_id)
    portfolio = client.get_portfolio(selected_portfolio_id)
    holdings = client.list_holdings(selected_portfolio_id)
    metrics = utils.portfolio_metrics(holdings, float(user.get("acct_balance", 0) or 0))
    holdings_df = utils.holdings_dataframe(holdings)

    _maybe_open_alerts_popup(client, selected_user_id)
    return AppContext(client, selected_user_id, selected_portfolio_id, user, portfolio, metrics, holdings_df)


# --- Formatting helpers ---------------------------------------------------

def fmt_currency(v: Any) -> str:
    if pd.isna(v):
        return "—"
    try:
        return utils.format_currency(float(v))
    except (TypeError, ValueError):
        return "—"


def fmt_pct(v: Any) -> str:
    if pd.isna(v):
        return "—"
    try:
        return f"{float(v):,.2f}%"
    except (TypeError, ValueError):
        return "—"


def fmt_ratio(v: Any) -> str:
    if pd.isna(v):
        return "—"
    try:
        return f"{float(v):,.2f}"
    except (TypeError, ValueError):
        return "—"


def spark_img(
    width: int = 140, height: int = 36, color: str = CHART_COLORS[0], accent: str = CHART_COLORS[4]
) -> str:
    """Inline decorative sparkline image."""
    return f'<img src="{spark_svg(width, height, color, accent)}" alt="" style="vertical-align:middle;"/>'


# --- Live ticker ----------------------------------------------------------

def live_ticker(client) -> None:
    """Render the scrolling live-prices marquee from the top stocks."""
    try:
        top_stocks = client.list_stocks(limit=10)
        top_ids = [int(s["stock_id"]) for s in top_stocks]
        top_quotes = {q["stock_id"]: q for q in client.get_stock_quotes(top_ids)}
        ticker_items = [
            (s["symbol"], utils.format_currency(float(top_quotes[int(s["stock_id"])]["price"])))
            for s in top_stocks
            if int(s["stock_id"]) in top_quotes and top_quotes[int(s["stock_id"])].get("price") is not None
        ]
        if ticker_items:
            st.markdown(ticker_html(ticker_items), unsafe_allow_html=True)
    except (APIError, KeyError, ValueError):
        pass


# --- Price helpers ---------------------------------------------------------

def tx_stock_label(row: dict[str, Any]) -> str:
    """Return the stock symbol (or name) for a transaction row, '—' if none."""
    symbol = row.get("symbol")
    if symbol:
        return str(symbol)
    name = row.get("short_name")
    if name:
        return str(name)
    return "—"


def price_series(candles: list[dict[str, Any]]) -> pd.Series:
    """Build a time-indexed close-price series from raw OHLC candle dicts."""
    if not candles:
        return pd.Series(dtype="float64")
    df = pd.DataFrame(candles)
    if "ts" not in df.columns and "timestamp" in df.columns:
        df["ts"] = df["timestamp"]
    df["ts"] = pd.to_datetime(df["ts"])
    df = df[utils.is_trading_day(df["ts"])].sort_values("ts").set_index("ts")
    close = pd.to_numeric(df["close"], errors="coerce")
    if "adj_close" in df.columns:
        adj = pd.to_numeric(df["adj_close"], errors="coerce")
        close = adj.fillna(close)
    close.name = "price"
    return close


def candles_dataframe(candles: list[dict[str, Any]]) -> pd.DataFrame:
    """Normalize raw candle dicts into a DataFrame with a ``ts`` column."""
    df = pd.DataFrame(candles)
    if "ts" not in df.columns and "timestamp" in df.columns:
        df["ts"] = df["timestamp"]
    df["ts"] = pd.to_datetime(df["ts"])
    return df[utils.is_trading_day(df["ts"])].reset_index(drop=True)


def price_candlestick_figure(candles_df: pd.DataFrame, symbol: str) -> go.Figure:
    """Candlestick OHLC chart with axes fit to the data points."""
    df = candles_df.copy()
    df["ts"] = pd.to_datetime(df["ts"])
    df = df.sort_values("ts").reset_index(drop=True)
    for col in ("open", "high", "low", "close"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"])

    fig = go.Figure(
        data=[
            go.Candlestick(
                x=df["ts"],
                open=df["open"],
                high=df["high"],
                low=df["low"],
                close=df["close"],
                increasing_line_color=CHART_COLORS[2],
                decreasing_line_color=CHART_COLORS[7],
                name=symbol,
            )
        ]
    )
    if df.empty:
        return fig

    y_lo = float(df["low"].min())
    y_hi = float(df["high"].max())
    pad = max((y_hi - y_lo) * 0.05, y_hi * 0.01, 0.01)
    x_lo = df["ts"].min()
    x_hi = df["ts"].max()

    fig.update_layout(**PLOTLY_LAYOUT, height=420, xaxis_rangeslider_visible=False)
    fig.update_yaxes(range=[y_lo - pad, y_hi + pad])
    fig.update_xaxes(range=[x_lo - pd.Timedelta(days=1), x_hi + pd.Timedelta(days=1)])
    return fig


# --- Alert check -----------------------------------------------------------

def run_check_now(client, selected_user_id: int, send_email: bool = False) -> Optional[dict[str, Any]]:
    """POST /alerts/check for the selected user; surfaces errors and results.

    ``send_email`` maps to the backend's ``sendEmail`` query param, which emails
    the generated alerts (or the pending unread ones) and marks them as read.
    """
    try:
        result = client.run_alert_check(selected_user_id, send_email=send_email)
    except APIError as exc:
        st.error(f"Alert check failed: {exc}")
        return None
    if result.get("alerts_created"):
        st.session_state["alerts_popup_shown"] = False
    return result


# --- Order confirmation dialog ---------------------------------------------

def _render_order_confirmation(client) -> None:
    """Body of the buy/sell confirmation screen: shows the full order detail
    (stock, quantity, live price, total) and only then executes the trade."""
    order = st.session_state.get("pending_order")
    if not order:
        st.info("No pending order.")
        return

    kind = order["kind"]
    symbol = order["symbol"]
    stock_id = order["stock_id"]
    portfolio_id = order.get("portfolio_id")
    quantity = int(order["quantity"])
    price = float(order["price"])
    total = quantity * price

    st.markdown(
        f"- **Action:** `{kind.upper()}`\n"
        f"- **Stock:** {symbol} (id {stock_id})\n"
        f"- **Quantity:** {quantity} share(s)\n"
        f"- **Live price:** {utils.format_currency(price)}\n"
        f"- **Estimated total:** {utils.format_currency(total)}"
    )

    col_confirm, col_cancel = st.columns(2)
    with col_confirm:
        confirm = st.button("Confirm", type="primary", width="stretch")
    with col_cancel:
        cancel = st.button("Cancel", width="stretch")

    if cancel:
        st.session_state.pop("pending_order", None)
        st.rerun()

    if confirm:
        try:
            if kind == "buy":
                client.buy_stock(portfolio_id, symbol, quantity, price)
                message = f"Purchased {quantity} share(s) of {symbol} at {utils.format_currency(price)}"
                basket = list(st.session_state.get("trade_basket", []))
                if symbol in basket:
                    basket.remove(symbol)
                st.session_state["trade_basket"] = basket
            else:
                client.sell_stock(portfolio_id, stock_id, quantity, price)
                message = f"Sold {quantity} share(s) of {symbol} at {utils.format_currency(price)}"
            st.session_state.pop("pending_order", None)
            st.session_state["trade_flash"] = message
            st.rerun()
        except APIError as exc:
            st.error(f"Order failed: {exc}")


def _dismiss_order_dialog() -> None:
    st.session_state.pop("pending_order", None)


if hasattr(st, "dialog"):
    try:
        _confirm_order_dialog = st.dialog("Confirm order", on_dismiss=_dismiss_order_dialog)(
            _render_order_confirmation
        )
    except TypeError:
        _confirm_order_dialog = st.dialog("Confirm order")(_render_order_confirmation)
else:
    _confirm_order_dialog = None


def confirm_order_dialog(client) -> None:
    """Open the order-confirmation dialog (or an expander on older Streamlit)."""
    if _confirm_order_dialog is not None:
        _confirm_order_dialog(client)
    else:
        with st.expander("Confirm order", expanded=True):
            _render_order_confirmation(client)


# --- Portfolio deletion dialog ----------------------------------------------

def _dismiss_delete_dialog() -> None:
    st.session_state.pop("confirm_delete_pending", None)


def _render_delete_portfolio(client, portfolio_id: int, portfolio_name: str) -> None:
    """Body of the delete-portfolio confirmation: lists every holding with its
    live price, requires selling all positions before deletion is allowed."""
    holdings = client.list_holdings(portfolio_id)

    if holdings:
        rows = []
        total_value = 0.0
        for h in holdings:
            qty = float(h.get("quantity") or 0)
            quote = client.get_stock_quote(int(h["stock_id"]))
            price = float(quote["price"]) if quote else None
            value = price * qty if price else None
            total_value += value or 0.0
            rows.append(
                {
                    "Symbol": h.get("symbol", ""),
                    "Quantity": qty,
                    "Live price": utils.format_currency(price) if price else "—",
                    "Value": utils.format_currency(value) if value else "—",
                }
            )
        st.warning(
            f"This portfolio still holds {len(holdings)} position(s). "
            "Sell all holdings below before it can be deleted."
        )
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        st.caption(f"Total market value: {utils.format_currency(total_value)}")

        if st.button("Sell all holdings at live price", type="primary", width="stretch"):
            try:
                for h in holdings:
                    stock_id = int(h["stock_id"])
                    qty = int(float(h.get("quantity") or 0))
                    quote = client.get_stock_quote(stock_id)
                    price = float(quote["price"]) if quote else None
                    if qty > 0 and price:
                        client.sell_stock(portfolio_id, stock_id, qty, price)
                st.rerun()
            except APIError as exc:
                st.error(f"Could not sell all holdings: {exc}")
        if st.button("Cancel", width="stretch"):
            st.session_state.pop("confirm_delete_pending", None)
            st.rerun()
    else:
        st.info(f"'{portfolio_name}' has no holdings left. You can delete it now.")
        col_del, col_cancel = st.columns(2)
        with col_del:
            delete_now = st.button("Delete portfolio", type="primary", width="stretch")
        with col_cancel:
            cancel = st.button("Cancel", width="stretch")
        if delete_now:
            try:
                client.delete_portfolio(portfolio_id)
                st.session_state.selected_portfolio_id = None
                st.session_state.pop("confirm_delete_pending", None)
                st.session_state["trade_flash"] = "Portfolio deleted."
                st.rerun()
            except APIError as exc:
                st.error(f"Could not delete portfolio: {exc}")
        if cancel:
            st.session_state.pop("confirm_delete_pending", None)
            st.rerun()


if hasattr(st, "dialog"):
    try:
        _delete_portfolio_dialog = st.dialog(
            "Delete portfolio", width="medium", on_dismiss=_dismiss_delete_dialog
        )(_render_delete_portfolio)
    except TypeError:
        _delete_portfolio_dialog = st.dialog("Delete portfolio", width="medium")(_render_delete_portfolio)
else:
    _delete_portfolio_dialog = None


def delete_portfolio_dialog(client, portfolio_id: int, portfolio_name: str) -> None:
    """Open the delete-portfolio confirmation dialog."""
    if _delete_portfolio_dialog is not None:
        _delete_portfolio_dialog(client, portfolio_id, portfolio_name)
    else:
        with st.expander("Delete portfolio", expanded=True):
            _render_delete_portfolio(client, portfolio_id, portfolio_name)


# --- Alerts popup dialog ----------------------------------------------------

def _render_alerts_popup(client, selected_user_id: int) -> None:
    """Popup warning listing the user's unread risk alerts."""
    try:
        payload = client.list_alerts(selected_user_id, unread_only=True, limit=50)
    except APIError as exc:
        st.error(f"Could not load alerts: {exc}")
        payload = {}

    alerts = payload.get("alerts") or []
    if not alerts:
        st.success("No unread alerts — all clear.")
    else:
        for alert in alerts:
            severity = str(alert.get("severity", "")).title()
            st.markdown(
                f"**[{severity}]** {alert.get('message', '')}  \n"
                f"_{alert.get('category', '').title()} · {alert.get('metric', '')} · "
                f"portfolio {alert.get('portfolio_id', '—')} · {str(alert.get('created_at', ''))[:19]}_"
            )

        ids = {a["alert_id"]: a["message"] for a in alerts}
        selected = st.multiselect(
            "Mark as read", options=list(ids.keys()),
            format_func=lambda i: f"#{i} · {ids[i][:70]}",
        )
        if st.button("Mark selected as read", width="stretch"):
            for alert_id in selected:
                try:
                    client.mark_alert_read(alert_id)
                except APIError:
                    pass
            st.session_state["alerts_popup_shown"] = True
            st.rerun()

    if st.button("Close", width="stretch"):
        st.session_state.pop("open_alerts_dialog", None)
        st.session_state["alerts_popup_shown"] = True
        st.rerun()


def _dismiss_alerts_dialog() -> None:
    st.session_state.pop("open_alerts_dialog", None)
    st.session_state["alerts_popup_shown"] = True


if hasattr(st, "dialog"):
    try:
        _alerts_dialog = st.dialog(
            "Risk alerts", width="medium", on_dismiss=_dismiss_alerts_dialog
        )(_render_alerts_popup)
    except TypeError:
        _alerts_dialog = st.dialog("Risk alerts", width="medium")(_render_alerts_popup)
else:
    _alerts_dialog = None


def alerts_dialog(client, selected_user_id: int) -> None:
    """Open the risk-alerts popup dialog (or an expander on older Streamlit)."""
    if _alerts_dialog is not None:
        _alerts_dialog(client, selected_user_id)
    else:
        with st.expander("Risk alerts", expanded=True):
            _render_alerts_popup(client, selected_user_id)
