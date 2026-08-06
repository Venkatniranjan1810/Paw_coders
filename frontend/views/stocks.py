"""Stocks page: discover stocks with live prices, price chart and comparison."""
from datetime import datetime
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import shared
import utils
from api_client import APIError
from shared import (
    candles_dataframe,
    fmt_currency,
    fmt_pct,
    live_ticker,
    price_candlestick_figure,
    spark_img,
)
from theme import PLOTLY_LAYOUT


def _stocks_live_table(client, search: Optional[str]) -> None:
    """Render the discover-stocks table with live prices.

    Auto-refreshes every minute (wrapped in a fragment below) so the latest
    live price is shown next to each stock row.
    """
    results = client.list_stocks(search=search or None, limit=100)
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
    styled = display.style.format({"Live price": fmt_currency, "Day change %": fmt_pct})
    st.dataframe(styled, width="stretch", hide_index=True)
    st.caption(f"Live prices refresh every minute · last update {datetime.now():%Y-%m-%d %H:%M:%S}")


def _build_live_fragment(client):
    """Wrap the live table so it refreshes every 60 seconds.

    The fragment is cached in session state so its identity stays stable
    across reruns (Streamlit requires a stable fragment function).
    """
    if "_stocks_live_fragment" not in st.session_state:
        if hasattr(st, "fragment"):
            try:
                st.session_state["_stocks_live_fragment"] = st.fragment(run_every=60)(
                    lambda search: _stocks_live_table(client, search)
                )
            except TypeError:
                st.session_state["_stocks_live_fragment"] = st.fragment(
                    lambda search: _stocks_live_table(client, search)
                )
        else:
            st.session_state["_stocks_live_fragment"] = lambda search: _stocks_live_table(client, search)
    return st.session_state["_stocks_live_fragment"]


def render(ctx) -> None:
    client = ctx.client
    live_ticker(client)
    st.markdown(
        f'**Discover stocks**'
        f'<span style="float:right">{spark_img(150, 38)}</span>',
        unsafe_allow_html=True,
    )
    discover_search = st.text_input("Search by symbol or name", key="discover_search")

    _build_live_fragment(client)(discover_search)

    discover_results = client.list_stocks(search=discover_search or None, limit=100)
    discover_df = pd.DataFrame(discover_results)

    if discover_df.empty:
        return

    st.divider()
    st.markdown("**Price chart**", unsafe_allow_html=True)
    symbol_options = discover_df["symbol"].tolist()
    chosen_symbol = st.selectbox("Stock", symbol_options, key="chart_symbol")
    chosen_stock = discover_df[discover_df["symbol"] == chosen_symbol].iloc[0]
    stock_id = int(chosen_stock["stock_id"])

    try:
        watchlist_symbols = {item["symbol"] for item in client.list_watchlist()}
    except APIError:
        watchlist_symbols = set()

    add_cols = st.columns(2)
    with add_cols[0]:
        if st.button(f"Add {chosen_symbol} to Trade basket", type="primary", width="stretch"):
            basket = list(st.session_state.trade_basket)
            if chosen_symbol not in basket:
                basket.append(chosen_symbol)
            st.session_state.trade_basket = basket
            st.session_state["buy_symbol_pending"] = chosen_symbol
            st.success(f"Added {chosen_symbol} to the Trade tab.")
            st.rerun()
    with add_cols[1]:
        if chosen_symbol in watchlist_symbols:
            st.caption(f"{chosen_symbol} is already in your watchlist.")
        elif st.button(f"Add {chosen_symbol} to Watchlist", width="stretch"):
            client.add_to_watchlist(chosen_symbol)
            st.success(f"Added {chosen_symbol} to the watchlist.")
            st.rerun()

    detail = client.get_stock(stock_id)
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

    price_params: dict[str, object] = {"interval": "1d", "limit": 5000}
    if chart_days:
        price_params["start"] = (pd.Timestamp.now() - pd.Timedelta(days=chart_days)).strftime("%Y-%m-%d")
    candles = client.get_stock_prices(stock_id, **price_params)
    if not candles:
        st.info(f"No price history for the selected period for {chosen_symbol}.")
    else:
        candles_df = candles_dataframe(candles)
        fig = price_candlestick_figure(candles_df, chosen_symbol)
        st.plotly_chart(fig, width="stretch")

    st.divider()
    st.markdown("**Compare stocks**", unsafe_allow_html=True)
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
            st.plotly_chart(compare_fig, width="stretch")


def main() -> None:
    """Streamlit page entrypoint."""
    ctx = shared.require_context()
    render(ctx)
