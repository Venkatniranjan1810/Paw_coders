"""Analytics page: P&L, risk metrics, allocation and return analytics."""
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import shared
import utils
from api_client import APIError
from shared import fmt_currency, fmt_ratio, live_ticker, price_series
from theme import CHART_COLORS, PLOTLY_LAYOUT


def render(ctx) -> None:
    client = ctx.client
    selected_user_id = ctx.selected_user_id
    selected_portfolio_id = ctx.selected_portfolio_id
    holdings_df = ctx.holdings_df

    live_ticker(client)
    if holdings_df.empty:
        st.info("Add holdings in the Trade tab to view analytics.")
        return

    try:
        pnl = client.get_portfolio_pnl(selected_portfolio_id)
    except APIError as exc:
        pnl = None
        st.error(f"P&L analytics unavailable: {exc}")

    if pnl:
        pcols = st.columns(4)
        pcols[0].metric("Market value", fmt_currency(pnl.get("total_market_value")))
        pcols[1].metric(
            "Total P/L",
            fmt_currency(pnl.get("total_pnl")),
            utils.format_pct(pnl.get("total_pnl_pct")),
        )
        pcols[2].metric("Unrealized P/L", fmt_currency(pnl.get("total_unrealized_pnl")))
        pcols[3].metric("Realized P/L", fmt_currency(pnl.get("total_realized_pnl")))

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
            st.markdown("**Portfolio P/L details**", unsafe_allow_html=True)
            st.dataframe(
                pnl_df.style.format(
                    {
                        "quantity": lambda v: f"{float(v):,.0f}",
                        "avg_buy_price": fmt_currency,
                        "current_price": fmt_currency,
                        "market_value": fmt_currency,
                        "unrealized_pnl": fmt_currency,
                        "unrealized_pnl_pct": utils.format_pct,
                        "realized_pnl": fmt_currency,
                        "total_pnl": fmt_currency,
                        "total_pnl_pct": utils.format_pct,
                    }
                ),
                width="stretch",
                hide_index=True,
            )

    st.markdown("**Risk metrics**", unsafe_allow_html=True)
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
                        "sharpe_ratio": fmt_ratio,
                    }
                ),
                width="stretch",
                hide_index=True,
            )
        else:
            st.info("No risk metrics available for this portfolio yet.")

    st.markdown("**Allocation**", unsafe_allow_html=True)
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
                st.plotly_chart(fig, width="stretch")
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
                st.plotly_chart(fig, width="stretch")
            else:
                st.caption("No quote-type data.")

    st.markdown("**Return analytics**", unsafe_allow_html=True)
    interval = "1d"
    price_series_by_symbol: dict[str, pd.Series] = {}
    analytics_rows: list[dict[str, Any]] = []

    for _, row in holdings_df.iterrows():
        symbol = row["symbol"]
        stock_id = int(row["stock_id"])
        candles = client.get_stock_prices(stock_id, interval=interval, limit=5000)
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
    st.dataframe(styled_analytics, width="stretch", hide_index=True)

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
            st.plotly_chart(fig, width="stretch")
        with chart_cols[1]:
            st.caption("Drawdown from peak")
            fig = go.Figure(
                data=[go.Scatter(x=dd.index, y=dd.values, mode="lines", fill="tozeroy", line=dict(color=CHART_COLORS[7], width=2))]
            )
            fig.update_layout(**PLOTLY_LAYOUT, height=320)
            dd_lo = float(dd.min())
            fig.update_yaxes(range=[dd_lo * 1.05, 0])
            st.plotly_chart(fig, width="stretch")

    st.divider()


def main() -> None:
    """Streamlit page entrypoint."""
    ctx = shared.require_context()
    render(ctx)
