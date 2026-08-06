"""Streamlit frontend for the QPMS FastAPI backend.

Run with: streamlit run frontend/app.py
"""
import os
import random
from datetime import datetime
from typing import Any, Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import api_client
import utils
from api_client import APIError, ApiClient
from theme import (
    CHART_COLORS,
    PLOTLY_LAYOUT,
    chart_svg,
    hero_html,
    inject_css,
    section_chip,
    spark_svg,
    ticker_html,
)

DEFAULT_BASE_URL = getattr(api_client, "DEFAULT_BASE_URL", "http://127.0.0.1:8001")

st.set_page_config(
    page_title="Portfolio Quant Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_css()


# --- State & client -----------------------------------------------------

def initialize_state() -> None:
    st.session_state.setdefault("api_base_url", os.getenv("API_BASE_URL", DEFAULT_BASE_URL))
    st.session_state.setdefault("selected_user_id", None)
    st.session_state.setdefault("selected_portfolio_id", None)
    st.session_state.setdefault("trade_basket", [])
    st.session_state.setdefault("pending_order", None)
    st.session_state.setdefault("trade_flash", None)


def get_client() -> ApiClient:
    return ApiClient(st.session_state.api_base_url)


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
    """Normalize raw candle dicts into a DataFrame with a ``ts`` column.

    Rows on non-trading days (weekends and US market holidays) are dropped so
    the price chart only shows real trading days.
    """
    df = pd.DataFrame(candles)
    if "ts" not in df.columns and "timestamp" in df.columns:
        df["ts"] = df["timestamp"]
    df["ts"] = pd.to_datetime(df["ts"])
    return df[utils.is_trading_day(df["ts"])].reset_index(drop=True)


def price_candlestick_figure(candles_df: pd.DataFrame, symbol: str) -> go.Figure:
    """Candlestick OHLC chart with axes fit to the data points.

    Y and X axis ranges are set to the min/max of the available data so the
    chart always frames the stock's performance for the selected range.
    """
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


def tx_stock_label(row: dict[str, Any]) -> str:
    """Return the stock symbol (or name) for a transaction row, '—' if none."""
    symbol = row.get("symbol")
    if symbol:
        return str(symbol)
    name = row.get("short_name")
    if name:
        return str(name)
    return "—"


# --- Table helpers -------------------------------------------------------

def _fmt_currency(v: Any) -> str:
    if pd.isna(v):
        return "—"
    try:
        return utils.format_currency(float(v))
    except (TypeError, ValueError):
        return "—"


def _fmt_pct(v: Any) -> str:
    if pd.isna(v):
        return "—"
    try:
        return f"{float(v):,.2f}%"
    except (TypeError, ValueError):
        return "—"


def _fmt_ratio(v: Any) -> str:
    if pd.isna(v):
        return "—"
    try:
        return f"{float(v):,.2f}"
    except (TypeError, ValueError):
        return "—"


def _spark_img(
    width: int = 140, height: int = 36, color: str = CHART_COLORS[0], accent: str = CHART_COLORS[4]
) -> str:
    """Inline decorative sparkline image."""
    return f'<img src="{spark_svg(width, height, color, accent)}" alt="" style="vertical-align:middle;"/>'


# --- Crazy features --------------------------------------------------------

_TRADE_EGGS = [
    "The stock market was literally invented under a tree in NYC.",
    "The first 'ticker tape' was actually used paper tape from telegraphs.",
    "A single share of Apple at its 1980 IPO would be worth more than 100 shares today.",
    "Bears hibernate, bulls charge — the terms come from how those animals attack.",
    "The NYSE had to close for months in 1914 due to World War I.",
    "Investing daily beats waiting for the 'perfect' moment more often than you'd think.",
    "The word 'stock' comes from the Old English 'stocc' meaning a tree stump.",
    "Legend says the Stock Exchange mascots were chosen because bulls toss UP and bears swipe DOWN.",
]


def _trade_easter_egg(symbol: str) -> str:
    """A silly coin-flip + fun fact appended to order confirmations."""
    coin = random.choice(["Heads", "Tails"])
    fact = random.choice(_TRADE_EGGS)
    return f"🪙 Coin flip: **{coin}**!\n\n> {fact}"


def _pet_panel(metrics: dict[str, float]) -> None:
    """A moody portfolio cat whose weight tracks your P/L."""
    equity = float(metrics["equity"] or 0)
    pnl_pct = float(metrics["pnl_pct"] or 0)
    if equity <= 0:
        face, mood, msg = "😿", "hollow", "No money, no kibble. The cat stares into the void."
    elif pnl_pct >= 15:
        face, mood, msg = "🐱", "CHONK", "The cat is eating premium tuna. Portfolio is THICC."
    elif pnl_pct >= 5:
        face, mood, msg = "🐱", "plump", "Purring hard — those gains are becoming belly."
    elif pnl_pct >= 0:
        face, mood, msg = "🐈", "content", "A calm cat. A flat day. Belly rubs all round."
    elif pnl_pct >= -10:
        face, mood, msg = "🐈‍⬛", "anxious", "The red numbers are stressing the cat out."
    elif pnl_pct >= -30:
        face, mood, msg = "🐈‍⬛", "skinny", "The cat went on a hunger strike. Please recover."
    else:
        face, mood, msg = "💀", "deceased", "The cat is a skeleton. It's that bad."
    st.markdown(
        f'<div class="pet-card">'
        f'<span class="pet-face">{face}</span>'
        f'<div class="pet-body"><b>Portfolio cat</b>'
        f'<div class="pet-msg">“{msg}”</div>'
        f'<span class="pet-mood">{mood}</span></div></div>'
        "<style>"
        ".pet-card{display:flex;align-items:center;gap:0.9rem;margin:0.2rem 0 1rem;"
        "background:linear-gradient(120deg,rgba(109,40,217,0.16),rgba(57,135,229,0.12));"
        "border:1px solid rgba(148,163,184,0.2);border-radius:14px;padding:0.7rem 1.1rem;"
        "box-shadow:0 6px 18px rgba(0,0,0,0.3);}"
        ".pet-face{font-size:2.1rem;}"
        ".pet-body{color:#cbd5e1;font-size:0.9rem;}"
        ".pet-body b{color:#f1f5f9;}"
        ".pet-msg{margin:0.1rem 0 0.3rem;color:#e2e8f0;}"
        ".pet-mood{display:inline-block;background:rgba(217,89,38,0.18);color:#fbbf24;"
        "font-size:0.7rem;font-weight:700;letter-spacing:0.06em;text-transform:uppercase;"
        "padding:0.15rem 0.6rem;border-radius:999px;}"
        "</style>",
        unsafe_allow_html=True,
    )


# --- Order confirmation ---------------------------------------------------

def _render_order_confirmation() -> None:
    """Body of the buy/sell confirmation screen: shows the full order detail
    (stock, quantity, live price, total) and only then executes the trade."""
    order = st.session_state.get("pending_order")
    if not order:
        st.info("No pending order.")
        return

    kind = order["kind"]
    symbol = order["symbol"]
    stock_id = order["stock_id"]
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
        confirm = st.button("Confirm", type="primary", use_container_width=True)
    with col_cancel:
        cancel = st.button("Cancel", use_container_width=True)

    if cancel:
        st.session_state.pop("pending_order", None)
        st.rerun()

    if confirm:
        try:
            if kind == "buy":
                client.buy_stock(selected_portfolio_id, symbol, quantity, price)
                message = f"Purchased {quantity} share(s) of {symbol} at {utils.format_currency(price)}"
                basket = list(st.session_state.get("trade_basket", []))
                if symbol in basket:
                    basket.remove(symbol)
                st.session_state["trade_basket"] = basket
            else:
                client.sell_stock(selected_portfolio_id, stock_id, quantity, price)
                message = f"Sold {quantity} share(s) of {symbol} at {utils.format_currency(price)}"
            st.session_state.pop("pending_order", None)
            st.session_state["trade_flash"] = f"{message}\n\n{_trade_easter_egg(symbol)}"
            st.rerun()
        except APIError as exc:
            st.error(f"Order failed: {exc}")


def _dismiss_order_dialog() -> None:
    st.session_state.pop("pending_order", None)


if hasattr(st, "dialog"):
    try:
        confirm_order_dialog = st.dialog("Confirm order", on_dismiss=_dismiss_order_dialog)(
            _render_order_confirmation
        )
    except TypeError:
        @st.dialog("Confirm order")
        def confirm_order_dialog() -> None:
            _render_order_confirmation()
else:
    def confirm_order_dialog() -> None:
        with st.expander("Confirm order", expanded=True):
            _render_order_confirmation()


# --- Portfolio deletion confirmation --------------------------------------

def _dismiss_delete_dialog() -> None:
    st.session_state.pop("confirm_delete_pending", None)


def _render_delete_portfolio(portfolio_id: int, portfolio_name: str) -> None:
    """Body of the delete-portfolio confirmation: lists every holding with its
    live price, requires selling all positions before deletion is allowed."""
    try:
        holdings = client.list_holdings(portfolio_id)
    except APIError as exc:
        st.error(f"Could not load holdings: {exc}")
        return

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
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.caption(f"Total market value: {utils.format_currency(total_value)}")

        if st.button("Sell all holdings at live price", type="primary", use_container_width=True):
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
        if st.button("Cancel", use_container_width=True):
            st.session_state.pop("confirm_delete_pending", None)
            st.rerun()
    else:
        st.info(f"'{portfolio_name}' has no holdings left. You can delete it now.")
        col_del, col_cancel = st.columns(2)
        with col_del:
            delete_now = st.button("Delete portfolio", type="primary", use_container_width=True)
        with col_cancel:
            cancel = st.button("Cancel", use_container_width=True)
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
        delete_portfolio_dialog = st.dialog(
            "Delete portfolio", width="medium", on_dismiss=_dismiss_delete_dialog
        )(_render_delete_portfolio)
    except TypeError:
        @st.dialog("Delete portfolio", width="medium")
        def delete_portfolio_dialog(portfolio_id: int, portfolio_name: str) -> None:
            _render_delete_portfolio(portfolio_id, portfolio_name)
else:
    def delete_portfolio_dialog(portfolio_id: int, portfolio_name: str) -> None:
        with st.expander("Delete portfolio", expanded=True):
            _render_delete_portfolio(portfolio_id, portfolio_name)


# --- Live stock prices (Stocks tab) ---------------------------------------

def _stocks_live_table(search: Optional[str]) -> None:
    """Render the discover-stocks table with live prices.

    Auto-refreshes every minute (wrapped in st.fragment below) so the latest
    live price is shown next to each stock row.
    """
    try:
        results = client.list_stocks(search=search or None, limit=100)
    except APIError as exc:
        st.error(f"Could not load stocks: {exc}")
        return
    df = pd.DataFrame(results)
    if df.empty:
        st.info("No matching stocks found.")
        return

    df["stock_id"] = df["stock_id"].astype(int)
    quotes = {q["stock_id"]: q["price"] for q in client.get_stock_quotes(df["stock_id"].tolist())}
    df["live_price"] = [
        float(quotes.get(int(stock_id))) if int(stock_id) in quotes else None
        for stock_id in df["stock_id"]
    ]
    db_close = pd.to_numeric(df.get("current_price"), errors="coerce")
    live = pd.Series(df["live_price"], dtype="float64")
    df["live_price"] = live.fillna(db_close)

    display = pd.DataFrame(
        {
            "Symbol": df["symbol"],
            "Name": df["short_name"].fillna(""),
            "Sector": df["sector"].fillna(""),
            "Live price": df["live_price"],
            "Day change %": pd.to_numeric(df.get("day_change_pct"), errors="coerce"),
        }
    )
    styled = display.style.format({"Live price": _fmt_currency, "Day change %": _fmt_pct})
    st.dataframe(styled, use_container_width=True, hide_index=True)
    st.caption(f"Live prices refresh every minute · last update {datetime.now():%Y-%m-%d %H:%M:%S}")


stocks_live_prices_fragment = _stocks_live_table
if hasattr(st, "fragment"):
    try:
        stocks_live_prices_fragment = st.fragment(run_every=60)(_stocks_live_table)
    except TypeError:
        stocks_live_prices_fragment = st.fragment(_stocks_live_table)


# --- App ------------------------------------------------------------------

initialize_state()
client = get_client()

st.markdown(
    hero_html(
        "Portfolio Quant Dashboard",
        "Track, trade and analyse your portfolio with live market data.",
    ),
    unsafe_allow_html=True,
)

try:
    health = client.health()
except APIError as exc:
    st.error(str(exc))
    st.info("Start the backend with: uvicorn main:app --reload  (run from the backend/ folder)")
    st.stop()

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

with st.sidebar:
    st.markdown(
        '<div class="sidebar-brand">🐾 Paw Coders<span>Quant Portfolio Suite</span></div>',
        unsafe_allow_html=True,
    )
    st.header("Controls")
    st.text_input("Backend URL", key="api_base_url")
    if st.button("Refresh data", use_container_width=True):
        st.rerun()

    st.divider()

    try:
        users = client.list_users()
    except APIError as exc:
        st.error(f"Could not load users: {exc}")
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
        st.selectbox(
            "User",
            options=[preferred_user["user_id"]],
            index=0,
            format_func=lambda uid: "Paw Coder",
            disabled=True,
            key="user_selector",
        )
    else:
        st.session_state.selected_user_id = None
        st.info("No users found in the database yet.")

    if st.session_state.selected_user_id is not None:
        try:
            portfolios = client.list_portfolios(int(st.session_state.selected_user_id))
        except APIError as exc:
            st.error(f"Could not load portfolios: {exc}")
            portfolios = []
        portfolio_ids = [p["portfolio_id"] for p in portfolios]
        portfolio_lookup = {p["portfolio_id"]: p for p in portfolios}
        if portfolio_ids:
            if st.session_state.selected_portfolio_id not in portfolio_ids:
                st.session_state.selected_portfolio_id = portfolio_ids[0]
            selected_portfolio_id = st.selectbox(
                "Portfolio",
                options=portfolio_ids,
                index=portfolio_ids.index(st.session_state.selected_portfolio_id),
                format_func=lambda pid: portfolio_lookup[pid].get("name", f"Portfolio {pid}"),
                key="portfolio_selector",
            )
            st.session_state.selected_portfolio_id = selected_portfolio_id
        else:
            st.session_state.selected_portfolio_id = None
            st.info("No portfolios yet for this user.")
    else:
        st.session_state.selected_portfolio_id = None

    with st.form("create_portfolio"):
        st.caption("Create a new portfolio")
        portfolio_name = st.text_input("Name", value="My Portfolio")
        submitted = st.form_submit_button("Create portfolio", use_container_width=True)
        if submitted and st.session_state.selected_user_id is not None:
            try:
                created_portfolio = client.create_portfolio(
                    int(st.session_state.selected_user_id), portfolio_name.strip() or "My Portfolio"
                )
                st.session_state.selected_portfolio_id = created_portfolio.get("portfolio_id")
                st.success("Portfolio created")
                st.rerun()
            except APIError as exc:
                st.error(str(exc))

if st.session_state.selected_user_id is None:
    st.info("No users exist yet — seed one via the backend/portfolio_db_setup scripts.")
    st.stop()

if st.session_state.selected_portfolio_id is None:
    st.info("Create a portfolio in the sidebar to get started.")
    st.stop()

selected_user_id = int(st.session_state.selected_user_id)
selected_portfolio_id = int(st.session_state.selected_portfolio_id)

try:
    user = client.get_user(selected_user_id)
    portfolio = client.get_portfolio(selected_portfolio_id)
    holdings = client.list_holdings(selected_portfolio_id)
except APIError as exc:
    st.error(f"Could not load portfolio data: {exc}")
    st.stop()
metrics = utils.portfolio_metrics(holdings, float(user.get("acct_balance", 0) or 0))
holdings_df = utils.holdings_dataframe(holdings)

st.subheader(f"{portfolio.get('name', 'Portfolio')} · Paw Coder")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Cash balance", utils.format_currency(metrics["cash_balance"]))
col2.metric("Holdings value", utils.format_currency(metrics["market_value"]))
col3.metric("Net equity", utils.format_currency(metrics["equity"]))
col4.metric("Unrealized P/L", utils.format_currency(metrics["pnl"]), utils.format_pct(metrics["pnl_pct"]))

_pet_panel(metrics)

dashboard_tab, trade_tab, stocks_tab, watchlist_tab, analytics_tab, transactions_tab = st.tabs(
    ["Dashboard", "Trade", "Stocks", "Watchlist", "Analytics", "Transactions"]
)

# --- Dashboard --------------------------------------------------------

with dashboard_tab:
    left, right = st.columns([3, 2])

    with left:
        st.markdown(f"{section_chip('📊')} **Holdings**", unsafe_allow_html=True)
        if holdings_df.empty:
            st.info("This portfolio has no holdings yet — buy a position in the Trade tab.")
        else:
            holdings_styled = holdings_df[
                ["symbol", "short_name", "quantity", "avg_buy_price", "price_live", "market_value", "unrealized_pnl"]
            ].sort_values("symbol").style.format(
                {
                    "avg_buy_price": _fmt_currency,
                    "price_live": _fmt_currency,
                    "market_value": _fmt_currency,
                    "unrealized_pnl": _fmt_currency,
                }
            )
            st.dataframe(holdings_styled, use_container_width=True, hide_index=True)

    with right:
        st.markdown(f"{section_chip('🥧')} **Allocation**", unsafe_allow_html=True)
        if holdings_df.empty or holdings_df["market_value"].sum() <= 0:
            st.info("No market value to chart yet.")
        else:
            alloc = holdings_df[holdings_df["market_value"] > 0]
            fig = go.Figure(
                data=[
                    go.Pie(
                        labels=alloc["symbol"],
                        values=alloc["market_value"],
                        hole=0.55,
                        marker=dict(colors=CHART_COLORS, line=dict(color="#ffffff", width=2)),
                        textinfo="label+percent",
                    )
                ]
            )
            fig.update_layout(**PLOTLY_LAYOUT, height=320, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

    st.markdown(f'{section_chip("🎯")} **Positions**', unsafe_allow_html=True)
    positions_df = holdings_df[holdings_df["is_position"]] if not holdings_df.empty else holdings_df
    if positions_df.empty:
        st.info("No open positions right now — positions open when you buy a stock and expire shortly after.")
    else:
        positions_styled = positions_df[
            ["symbol", "short_name", "quantity", "avg_buy_price", "price_live", "market_value", "unrealized_pnl"]
        ].sort_values("symbol").style.format(
            {
                "avg_buy_price": _fmt_currency,
                "price_live": _fmt_currency,
                "market_value": _fmt_currency,
                "unrealized_pnl": _fmt_currency,
            }
        )
        st.dataframe(positions_styled, use_container_width=True, hide_index=True)

    st.markdown(
        f'{section_chip("🕑")} **Recent transactions**'
        f'<span style="float:right">{_spark_img(150, 38, CHART_COLORS[5], CHART_COLORS[3])}</span>',
        unsafe_allow_html=True,
    )
    try:
        recent_tx = client.list_transactions(selected_portfolio_id, limit=10)
    except TypeError:
        recent_tx = client.list_transactions(selected_portfolio_id)
    except APIError as exc:
        st.error(f"Could not load recent transactions: {exc}")
        recent_tx = []
    if recent_tx:
        tx_df = pd.DataFrame(recent_tx)
        tx_df["ts"] = pd.to_datetime(tx_df["ts"])
        tx_display = tx_df.copy()
        tx_display["stock"] = tx_df.apply(tx_stock_label, axis=1)
        tx_display["price"] = pd.to_numeric(tx_display["price"], errors="coerce")
        tx_display["amount"] = pd.to_numeric(tx_display["amount"], errors="coerce")
        tx_styled = tx_display[["trans_type", "stock", "quantity", "price", "amount", "ts"]].style.format(
            {"price": _fmt_currency, "amount": _fmt_currency}
        )
        st.dataframe(tx_styled, use_container_width=True, hide_index=True)
    else:
        st.info("No transactions yet.")

    st.divider()
    with st.expander("⚠️ Danger zone"):
        st.caption(
            f"Delete portfolio '{portfolio.get('name')}' — this permanently removes the "
            "portfolio together with its holdings and transaction history. This cannot be undone."
        )
        confirm_delete = st.checkbox("I understand this permanently deletes the portfolio")
        if st.button("Delete this portfolio", disabled=not confirm_delete):
            st.session_state["confirm_delete_pending"] = True
            st.rerun()

    if st.session_state.get("confirm_delete_pending") and not st.session_state.get("pending_order"):
        delete_portfolio_dialog(selected_portfolio_id, portfolio.get("name", ""))

# --- Trade --------------------------------------------------------------

with trade_tab:
    flash = st.session_state.pop("trade_flash", None)
    if flash:
        st.success(flash)

    st.markdown(
        f'{section_chip("⚡")} **Trade**'
        f'<span style="float:right">{_spark_img(150, 38, CHART_COLORS[6], CHART_COLORS[1])}</span>',
        unsafe_allow_html=True,
    )

    basket_click_pending = st.session_state.pop("basket_click_pending", None)
    if basket_click_pending:
        st.session_state["trade_search"] = basket_click_pending
        st.session_state["buy_symbol_pending"] = basket_click_pending

    stock_search = st.text_input("Search stocks to trade (symbol or name)", key="trade_search")
    try:
        stocks = client.list_stocks(search=stock_search or None, limit=200)
    except APIError as exc:
        st.error(f"Could not load stocks: {exc}")
        stocks = []
    stock_lookup = {s["symbol"]: s for s in stocks}
    stock_symbols = sorted(stock_lookup.keys())

    trade_basket = list(st.session_state.trade_basket)
    if trade_basket:
        with st.expander(f"🎯 Trade basket ({len(trade_basket)} stock(s) from the Stocks tab)", expanded=True):
            st.caption("Click a stock to load it in 'Buy a position' below.")
            for sym in list(trade_basket):
                c1, c2 = st.columns([4, 1])
                with c1:
                    if st.button(f"**{sym}**", key=f"select_{sym}", use_container_width=True):
                        st.session_state["basket_click_pending"] = sym
                        st.rerun()
                with c2:
                    if st.button("Remove", key=f"remove_{sym}", use_container_width=True):
                        basket = list(st.session_state.trade_basket)
                        if sym in basket:
                            basket.remove(sym)
                        st.session_state.trade_basket = basket
                        st.rerun()

    col_a, col_b = st.columns(2)
    with col_a:
        with st.expander("🛒 Buy a position", expanded=True):
            if not stock_symbols:
                st.info("No stocks match your search.")
            else:
                ordered_symbols = [s for s in trade_basket if s in stock_lookup] + [
                    s for s in stock_symbols if s not in trade_basket
                ]
                buy_index = 0
                if "buy_symbol_pending" in st.session_state:
                    pending = st.session_state.pop("buy_symbol_pending")
                    if pending not in ordered_symbols:
                        try:
                            candidates = client.list_stocks(search=pending, limit=5)
                        except APIError as exc:
                            st.error(f"Could not look up {pending}: {exc}")
                            candidates = []
                        for candidate in candidates:
                            if candidate.get("symbol") == pending:
                                stock_lookup[pending] = candidate
                                ordered_symbols.insert(0, pending)
                                break
                    if pending in ordered_symbols:
                        st.session_state.pop("buy_symbol", None)
                        buy_index = ordered_symbols.index(pending)
                buy_symbol = st.selectbox("Stock", ordered_symbols, index=buy_index, key="buy_symbol")
                selected_stock = stock_lookup.get(buy_symbol)
                quote_price = None
                if selected_stock:
                    quote = client.get_stock_quote(int(selected_stock["stock_id"]))
                    if quote:
                        quote_price = float(quote["price"])
                        st.caption(f"Live price from API: {utils.format_currency(quote_price)}")
                    else:
                        st.caption("Live price unavailable")

                with st.form("buy_form"):
                    buy_quantity = st.number_input(
                        "Quantity (whole shares only)",
                        min_value=1,
                        step=1,
                        value=1,
                        format="%d",
                    )
                    buy_submitted = st.form_submit_button("Buy stock")
                if buy_submitted:
                    if selected_stock is None:
                        st.error("Please select a valid stock.")
                    elif quote_price is None:
                        st.error("Live price unavailable for this stock — cannot place an order.")
                    else:
                        st.session_state["pending_order"] = {
                            "kind": "buy",
                            "stock_id": int(selected_stock["stock_id"]),
                            "symbol": buy_symbol,
                            "quantity": int(buy_quantity),
                            "price": quote_price,
                        }

    with col_b:
        if holdings_df.empty:
            st.caption("You don't own any stocks yet — nothing to sell.")
        else:
            with st.expander("📉 Sell a position", expanded=True):
                open_positions = {row["symbol"]: row for _, row in holdings_df.iterrows()}
                sell_symbol = st.selectbox("Holding to sell", list(open_positions.keys()), key="sell_symbol")
                selected_holding = open_positions[sell_symbol]

                sell_quote_price = None
                quote = client.get_stock_quote(int(selected_holding["stock_id"]))
                if quote:
                    sell_quote_price = float(quote["price"])
                    st.caption(f"Live price from API: {utils.format_currency(sell_quote_price)}")
                else:
                    st.caption("Live price unavailable")

                max_quantity = max(1, int(float(selected_holding["quantity"])))
                with st.form("sell_form"):
                    sell_all = st.checkbox("Sell full position")
                    sell_quantity = st.number_input(
                        "Quantity to sell (whole shares only)",
                        min_value=1,
                        max_value=max_quantity,
                        step=1,
                        value=min(1, max_quantity),
                        format="%d",
                        disabled=sell_all,
                    )
                    sell_submitted = st.form_submit_button("Sell stock")
                if sell_submitted:
                    if sell_quote_price is None:
                        st.error("Live price unavailable for this stock — cannot place an order.")
                    else:
                        sell_qty = max_quantity if sell_all else int(sell_quantity)
                        st.session_state["pending_order"] = {
                            "kind": "sell",
                            "stock_id": int(selected_holding["stock_id"]),
                            "symbol": sell_symbol,
                            "quantity": sell_qty,
                            "price": sell_quote_price,
                        }

    if st.session_state.get("pending_order"):
        confirm_order_dialog()

# --- Stocks -------------------------------------------------------------

with stocks_tab:
    st.markdown(
        f'{section_chip("🔎")} **Discover stocks**'
        f'<span style="float:right">{_spark_img(150, 38, CHART_COLORS[2], CHART_COLORS[3])}</span>',
        unsafe_allow_html=True,
    )
    discover_search = st.text_input("Search by symbol or name", key="discover_search")

    stocks_live_prices_fragment(discover_search)

    try:
        discover_results = client.list_stocks(search=discover_search or None, limit=100)
    except APIError as exc:
        st.error(f"Could not load stocks: {exc}")
        discover_results = []
    discover_df = pd.DataFrame(discover_results)

    if not discover_df.empty:
        st.divider()
        st.markdown(
            f'{section_chip("🧺")} **Add stocks to Trade**'
            f'<span style="float:right">{_spark_img(120, 32, CHART_COLORS[1], CHART_COLORS[0])}</span>',
            unsafe_allow_html=True,
        )
        discover_symbols = discover_df["symbol"].tolist()
        trade_selection = st.multiselect(
            "Select stocks, then add them to the Trade tab",
            options=discover_symbols,
            placeholder="Choose one or more stocks…",
        )
        try:
            watchlist_symbols = {item["symbol"] for item in client.list_watchlist()}
        except APIError:
            watchlist_symbols = set()
        add_cols = st.columns(2)
        with add_cols[0]:
            if st.button("Add to Trade basket", type="primary", use_container_width=True):
                if not trade_selection:
                    st.warning("Select at least one stock first.")
                else:
                    basket = list(st.session_state.trade_basket)
                    added_symbols = []
                    for sym in trade_selection:
                        if sym not in basket:
                            basket.append(sym)
                            added_symbols.append(sym)
                    st.session_state.trade_basket = basket
                    if added_symbols:
                        st.session_state["buy_symbol_pending"] = added_symbols[0]
                    st.success(f"Added {', '.join(trade_selection)} to the Trade tab.")
                    st.rerun()
        with add_cols[1]:
            if st.button("Add to Watchlist", use_container_width=True):
                if not trade_selection:
                    st.warning("Select at least one stock first.")
                else:
                    for sym in trade_selection:
                        if sym not in watchlist_symbols:
                            try:
                                client.add_to_watchlist(sym)
                            except APIError as exc:
                                st.error(f"Could not add {sym} to watchlist: {exc}")
                                continue
                            watchlist_symbols.add(sym)
                    st.success(f"Added {', '.join(trade_selection)} to the watchlist.")
                    st.rerun()

        st.divider()
        st.markdown(f'{section_chip("📉")} **Price chart**', unsafe_allow_html=True)
        symbol_options = discover_df["symbol"].tolist()
        chosen_symbol = st.selectbox("Stock", symbol_options, key="chart_symbol")
        chosen_stock = discover_df[discover_df["symbol"] == chosen_symbol].iloc[0]
        stock_id = int(chosen_stock["stock_id"])

        if st.button(f"➕ Add {chosen_symbol} to Trade basket"):
            basket = list(st.session_state.trade_basket)
            if chosen_symbol not in basket:
                basket.append(chosen_symbol)
            st.session_state.trade_basket = basket
            st.session_state["buy_symbol_pending"] = chosen_symbol
            st.success(f"Added {chosen_symbol} to the Trade tab.")
            st.rerun()

        if chosen_symbol in watchlist_symbols:
            st.caption(f"👀 {chosen_symbol} is already in your watchlist.")
        elif st.button(f"👀 Add {chosen_symbol} to Watchlist"):
            try:
                client.add_to_watchlist(chosen_symbol)
                watchlist_symbols.add(chosen_symbol)
                st.success(f"Added {chosen_symbol} to the watchlist.")
                st.rerun()
            except APIError as exc:
                st.error(f"Could not add {chosen_symbol} to watchlist: {exc}")

        try:
            detail = client.get_stock(stock_id)
        except APIError as exc:
            st.warning(f"Stock detail unavailable: {exc}")
            detail = {}
        quote = client.get_stock_quote(stock_id)

        info_cols = st.columns(4)
        info_cols[0].metric("Live price", utils.format_currency(float(quote["price"])) if quote else "n/a")
        info_cols[1].metric("Exchange", detail.get("exchange") or "n/a")
        info_cols[2].metric("Industry", detail.get("industry") or "n/a")
        info_cols[3].metric("Currency", detail.get("currency") or "n/a")

        chart_periods = {
            "1 month": 30,
            "3 months": 90,
            "6 months": 180,
            "1 year": 365,
            "2 years": 730,
            "Max available": None,
        }
        chart_period = st.selectbox("Period", list(chart_periods), key="chart_period")
        chart_days = chart_periods[chart_period]

        price_params: dict[str, Any] = {"interval": "1d", "limit": 5000}
        if chart_days:
            price_params["start"] = (pd.Timestamp.now() - pd.Timedelta(days=chart_days)).strftime("%Y-%m-%d")
        try:
            candles = client.get_stock_prices(stock_id, **price_params)
        except APIError as exc:
            st.error(f"Could not load price history: {exc}")
            candles = []
        if not candles:
            st.info(f"No price history for the selected period for {chosen_symbol}.")
        else:
            candles_df = candles_dataframe(candles)
            fig = price_candlestick_figure(candles_df, chosen_symbol)
            st.plotly_chart(fig, use_container_width=True)

        st.divider()
        st.markdown(f'{section_chip("⚖️")} **Compare stocks**', unsafe_allow_html=True)
        if len(symbol_options) < 2:
            st.info("Need at least two stocks in the list to compare.")
        else:
            cmp_cols = st.columns(2)
            with cmp_cols[0]:
                cmp_symbol_a = st.selectbox("Stock A", symbol_options, key="cmp_a", index=0)
            with cmp_cols[1]:
                cmp_symbol_b = st.selectbox(
                    "Stock B",
                    symbol_options,
                    key="cmp_b",
                    index=1 if len(symbol_options) > 1 else 0,
                )
            cmp_stock_a = discover_df[discover_df["symbol"] == cmp_symbol_a].iloc[0]
            cmp_stock_b = discover_df[discover_df["symbol"] == cmp_symbol_b].iloc[0]

            compare_intervals = {"1 day": "1d", "1 week": "1w", "1 month": "1mo", "1 year": "1y"}
            compare_ranges = {
                "All history": "all",
                "Last day": "last_day",
                "Last week": "last_week",
                "Last month": "last_month",
                "Last 6 months": "last_6_months",
                "Last 1 year": "last_1_year",
                "Last 5 years": "last_5_years",
            }
            cmp_cols2 = st.columns(2)
            with cmp_cols2[0]:
                cmp_interval = st.selectbox("Interval", list(compare_intervals), key="cmp_interval")
            with cmp_cols2[1]:
                cmp_range = st.selectbox("Range", list(compare_ranges), key="cmp_range")

            try:
                compare_data = client.compare_stock_prices(
                    int(cmp_stock_a["stock_id"]),
                    int(cmp_stock_b["stock_id"]),
                    interval=compare_intervals[cmp_interval],
                    range_name=compare_ranges[cmp_range],
                )
            except APIError as exc:
                compare_data = None
                st.error(str(exc))

            if not compare_data or not compare_data.get("series"):
                st.info("No comparable price history for the selected period.")
            else:
                range_label = compare_data.get("range_label")
                if range_label:
                    st.caption(f"Range: {range_label}")
                compare_fig = go.Figure()
                for series in compare_data["series"]:
                    candles_df = candles_dataframe(series["candles"])
                    compare_fig.add_trace(
                        go.Scatter(
                            x=candles_df["ts"],
                            y=pd.to_numeric(candles_df["close"], errors="coerce"),
                            mode="lines",
                            name=series.get("symbol"),
                            line=dict(width=2),
                        )
                    )
                compare_fig.update_layout(**PLOTLY_LAYOUT, height=380)
                st.plotly_chart(compare_fig, use_container_width=True)

# --- Watchlist ---------------------------------------------------------

with watchlist_tab:
    st.markdown(
        f'{section_chip("👀")} **Watchlist**'
        f'<span style="float:right">{_spark_img(150, 38, CHART_COLORS[0], CHART_COLORS[5])}</span>',
        unsafe_allow_html=True,
    )

    add_col, add_btn_col = st.columns([3, 1])
    with add_col:
        watch_symbol = st.text_input(
            "Add a stock by symbol",
            placeholder="e.g. AAPL, MSFT, TSLA…",
            key="watch_symbol_input",
        ).strip().upper()
    with add_btn_col:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Add to Watchlist", type="primary", use_container_width=True):
            if not watch_symbol:
                st.warning("Enter a stock symbol first.")
            else:
                try:
                    client.add_to_watchlist(watch_symbol)
                    st.success(f"Added {watch_symbol} to the watchlist.")
                    st.rerun()
                except APIError as exc:
                    st.error(str(exc))

    try:
        watchlist = client.list_watchlist()
    except APIError as exc:
        watchlist = []
        st.error(str(exc))

    if not watchlist:
        st.info("Your watchlist is empty — add stocks from the Stocks tab or by symbol above.")
    else:
        watch_df = pd.DataFrame(watchlist)
        for col in ("current_price", "previous_close", "day_change", "day_change_pct"):
            watch_df[col] = pd.to_numeric(watch_df[col], errors="coerce")
        watch_styled = watch_df[
            ["symbol", "short_name", "sector", "current_price", "day_change", "day_change_pct"]
        ].style.format(
            {
                "current_price": _fmt_currency,
                "day_change": _fmt_currency,
                "day_change_pct": _fmt_pct,
            }
        )
        st.dataframe(watch_styled, use_container_width=True, hide_index=True)

        rm_col, rm_btn_col = st.columns([3, 1])
        with rm_col:
            remove_symbol = st.selectbox(
                "Remove from watchlist", watch_df["symbol"].tolist(), key="watch_remove_symbol"
            )
        with rm_btn_col:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Remove", key="watch_remove_btn", use_container_width=True):
                try:
                    row = watch_df[watch_df["symbol"] == remove_symbol].iloc[0]
                    client.remove_from_watchlist(int(row["stock_id"]))
                    st.success(f"Removed {remove_symbol} from the watchlist.")
                    st.rerun()
                except APIError as exc:
                    st.error(str(exc))

# --- Analytics --------------------------------------------------------

with analytics_tab:
    st.markdown(f"{section_chip('📈')} **Portfolio analytics**", unsafe_allow_html=True)
    if holdings_df.empty:
        st.info("Add holdings in the Trade tab to view analytics.")
    else:
        try:
            pnl = client.get_portfolio_pnl(selected_portfolio_id)
        except APIError as exc:
            pnl = None
            st.error(f"P&L analytics unavailable: {exc}")

        if pnl:
            st.markdown(f"{section_chip('💰')} **P&L summary**", unsafe_allow_html=True)
            pcols = st.columns(4)
            pcols[0].metric("Market value", _fmt_currency(pnl.get("total_market_value")))
            pcols[1].metric(
                "Total P/L",
                _fmt_currency(pnl.get("total_pnl")),
                utils.format_pct(pnl.get("total_pnl_pct")),
            )
            pcols[2].metric("Unrealized P/L", _fmt_currency(pnl.get("total_unrealized_pnl")))
            pcols[3].metric("Realized P/L", _fmt_currency(pnl.get("total_realized_pnl")))

            pnl_rows: list[dict[str, Any]] = []
            for h in pnl.get("holdings", []):
                pnl_rows.append(
                    {
                        "symbol": h.get("symbol"),
                        "quantity": h.get("quantity"),
                        "avg_buy_price": h.get("avg_buy_price"),
                        "current_price": h.get("current_price"),
                        "market_value": h.get("market_value"),
                        "unrealized_pnl": h.get("unrealized_pnl"),
                        "unrealized_pnl_pct": h.get("unrealized_pnl_pct"),
                        "realized_pnl": h.get("realized_pnl"),
                        "total_pnl": h.get("total_pnl"),
                        "total_pnl_pct": h.get("total_pnl_pct"),
                    }
                )
            pnl_df = pd.DataFrame(pnl_rows)
            if not pnl_df.empty:
                st.dataframe(
                    pnl_df.style.format(
                        {
                            "quantity": lambda v: f"{float(v):,.0f}",
                            "avg_buy_price": _fmt_currency,
                            "current_price": _fmt_currency,
                            "market_value": _fmt_currency,
                            "unrealized_pnl": _fmt_currency,
                            "unrealized_pnl_pct": utils.format_pct,
                            "realized_pnl": _fmt_currency,
                            "total_pnl": _fmt_currency,
                            "total_pnl_pct": utils.format_pct,
                        }
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

        st.markdown(f"{section_chip('🛡️')} **Risk metrics**", unsafe_allow_html=True)
        try:
            risk_payload = client.get_portfolios_risk(selected_user_id)
        except APIError as exc:
            risk_payload = None
            st.error(f"Risk metrics unavailable: {exc}")
        if risk_payload:
            risk_rows: list[dict[str, Any]] = []
            for p in risk_payload.get("portfolios", []):
                if int(p.get("portfolio_id")) != selected_portfolio_id:
                    continue
                metrics_r = p.get("metrics") or {}
                risk_rows.append(
                    {
                        "annualized_return": metrics_r.get("annualized_return"),
                        "annualized_volatility": metrics_r.get("annualized_volatility"),
                        "sharpe_ratio": metrics_r.get("sharpe_ratio"),
                        "max_drawdown": metrics_r.get("max_drawdown"),
                        "value_at_risk_95": metrics_r.get("value_at_risk_95"),
                        "value_at_risk_99": metrics_r.get("value_at_risk_99"),
                        "beta": metrics_r.get("beta"),
                    }
                )
            if risk_rows:
                risk_df = pd.DataFrame(risk_rows)
                st.dataframe(
                    risk_df.style.format(
                        {
                            "annualized_return": utils.format_pct,
                            "annualized_volatility": utils.format_pct,
                            "max_drawdown": utils.format_pct,
                            "value_at_risk_95": utils.format_pct,
                            "value_at_risk_99": utils.format_pct,
                            "sharpe_ratio": _fmt_ratio,
                            "beta": _fmt_ratio,
                        }
                    ),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("No risk metrics available for this portfolio yet.")

        st.markdown(f"{section_chip('🥧')} **Allocation**", unsafe_allow_html=True)
        try:
            alloc_sector = client.get_allocation(selected_portfolio_id, by="sector")
            alloc_qtype = client.get_allocation(selected_portfolio_id, by="quote-type")
        except APIError:
            alloc_sector = None
            alloc_qtype = None
        if alloc_sector or alloc_qtype:
            acol1, acol2 = st.columns(2)
            with acol1:
                st.caption("Holdings by sector")
                sector_groups = (alloc_sector or {}).get("groups") or []
                if sector_groups:
                    fig = go.Figure(
                        data=[
                            go.Pie(
                                labels=[g["label"] for g in sector_groups],
                                values=[g["holdings_count"] for g in sector_groups],
                                hole=0.5,
                                marker=dict(colors=CHART_COLORS),
                                textinfo="label+value",
                            )
                        ]
                    )
                    fig.update_layout(**PLOTLY_LAYOUT, height=320, showlegend=False)
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.caption("No sector data.")
            with acol2:
                st.caption("Holdings by quote type")
                qtype_groups = (alloc_qtype or {}).get("groups") or []
                if qtype_groups:
                    fig = go.Figure(
                        data=[
                            go.Pie(
                                labels=[g["label"] for g in qtype_groups],
                                values=[g["holdings_count"] for g in qtype_groups],
                                hole=0.5,
                                marker=dict(colors=CHART_COLORS[2:] + CHART_COLORS[:2]),
                                textinfo="label+value",
                            )
                        ]
                    )
                    fig.update_layout(**PLOTLY_LAYOUT, height=320, showlegend=False)
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.caption("No quote-type data.")

        st.markdown(f"{section_chip('📊')} **Return analytics**", unsafe_allow_html=True)
        interval = "1d"
        price_series_by_symbol: dict[str, pd.Series] = {}
        analytics_rows: list[dict[str, Any]] = []

        for _, row in holdings_df.iterrows():
            symbol = row["symbol"]
            stock_id = int(row["stock_id"])
            try:
                candles = client.get_stock_prices(stock_id, interval=interval, limit=5000)
            except APIError:
                candles = []
            series = price_series(candles)
            price_series_by_symbol[symbol] = series
            result = utils.analyze_prices(series, interval=interval)
            analytics_rows.append(
                {
                    "symbol": symbol,
                    "total_return": result["total_return"],
                    "annualized_return": result["annualized_return"],
                    "annualized_volatility": result["annualized_volatility"],
                    "sharpe_ratio": result["sharpe_ratio"],
                    "max_drawdown": result["max_drawdown"],
                }
            )

        analytics_df = pd.DataFrame(analytics_rows)
        styled_analytics = analytics_df.style.format(
            {
                "total_return": utils.format_pct,
                "annualized_return": utils.format_pct,
                "annualized_volatility": utils.format_pct,
                "max_drawdown": utils.format_pct,
                "sharpe_ratio": lambda v: f"{float(v):,.2f}",
            }
        )
        st.dataframe(styled_analytics, use_container_width=True, hide_index=True)

        weights = {
            row["symbol"]: float(row["market_value"])
            for _, row in holdings_df.iterrows()
            if float(row["market_value"] or 0) > 0
        }
        wi = utils.portfolio_wealth_index(price_series_by_symbol, weights)

        if wi.empty:
            st.info("Not enough shared price history across holdings to build a portfolio wealth curve.")
        else:
            dd = utils.drawdown(wi)
            chart_cols = st.columns(2)
            with chart_cols[0]:
                st.caption("Wealth index (growth of $1, weighted by market value)")
                fig = go.Figure(data=[go.Scatter(x=wi.index, y=wi.values, mode="lines", line=dict(color=CHART_COLORS[0], width=2))])
                fig.update_layout(**PLOTLY_LAYOUT, height=320)
                wi_lo = float(wi.min())
                wi_hi = float(wi.max())
                wi_pad = max((wi_hi - wi_lo) * 0.1, wi_hi * 0.01, 0.01)
                fig.update_yaxes(range=[wi_lo - wi_pad, wi_hi + wi_pad])
                st.plotly_chart(fig, use_container_width=True)
            with chart_cols[1]:
                st.caption("Drawdown from peak")
                fig = go.Figure(
                    data=[go.Scatter(x=dd.index, y=dd.values, mode="lines", fill="tozeroy", line=dict(color=CHART_COLORS[7], width=2))]
                )
                fig.update_layout(**PLOTLY_LAYOUT, height=320)
                dd_lo = float(dd.min())
                fig.update_yaxes(range=[dd_lo * 1.05, 0])
                st.plotly_chart(fig, use_container_width=True)

        st.divider()

# --- Transactions -------------------------------------------------------

with transactions_tab:
    st.markdown(f"{section_chip('🧾')} **Transaction history**", unsafe_allow_html=True)

    type_filter = st.selectbox("Type", ["All", "BUY", "SELL", "DEPOSIT", "WITHDRAW", "DIVIDEND"])

    history_params: dict[str, Any] = {
        "range_name": "all",
        "start_date": None,
        "end_date": None,
        "trans_type": None if type_filter == "All" else type_filter,
    }

    try:
        tx_history = client.list_transactions_history(selected_portfolio_id, **history_params)
        transactions = tx_history.get("transactions", [])
    except APIError as exc:
        st.error(str(exc))
        transactions = []

    try:
        report_bytes = client.download_transactions_report(selected_portfolio_id, **history_params)
        st.download_button(
            "⬇️ Download PDF report",
            data=report_bytes,
            file_name=f"transactions_{selected_portfolio_id}.pdf",
            mime="application/pdf",
        )
    except APIError as exc:
        st.warning(f"PDF report unavailable: {exc}")

    if not transactions:
        st.info("No transactions match this filter.")
    else:
        mcol1, mcol2 = st.columns(2)
        mcol1.metric("Transactions", len(transactions))
        mcol2.metric("Net flow", utils.format_currency(float(tx_history.get("total_amount") or 0)))

        tx_df = pd.DataFrame(transactions)
        tx_df["ts"] = pd.to_datetime(tx_df["ts"])
        tx_display = tx_df.copy()
        tx_display["stock"] = tx_df.apply(tx_stock_label, axis=1)
        tx_display["price"] = pd.to_numeric(tx_display["price"], errors="coerce")
        tx_display["amount"] = pd.to_numeric(tx_display["amount"], errors="coerce")
        tx_styled = tx_display[
            ["trans_id", "trans_type", "stock", "quantity", "price", "amount", "trans_details", "ts"]
        ].style.format({"price": _fmt_currency, "amount": _fmt_currency})
        st.dataframe(tx_styled, use_container_width=True, hide_index=True)
