"""Dashboard page: portfolio overview, holdings, allocation, positions."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import shared
import utils
from shared import fmt_currency, live_ticker
from theme import CHART_COLORS, PLOTLY_LAYOUT, hero_html


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


def render(ctx) -> None:
    client = ctx.client
    portfolio = ctx.portfolio
    metrics = ctx.metrics
    holdings_df = ctx.holdings_df
    selected_portfolio_id = ctx.selected_portfolio_id
    delete_portfolio_dialog = shared.delete_portfolio_dialog

    live_ticker(client)
    st.subheader(f"{portfolio.get('name', 'Portfolio')} · Paw Coder")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Cash balance", utils.format_currency(metrics["cash_balance"]))
    col2.metric("Holdings value", utils.format_currency(metrics["market_value"]))
    col3.metric("Net equity", utils.format_currency(metrics["equity"]))
    col4.metric("Unrealized P/L", utils.format_currency(metrics["pnl"]), utils.format_pct(metrics["pnl_pct"]))

    _pet_panel(metrics)

    left, right = st.columns([3, 2])

    with left:
        st.markdown("**Holdings**", unsafe_allow_html=True)
        if holdings_df.empty:
            st.info("This portfolio has no holdings yet — buy a position in the Trade tab.")
        else:
            holdings_styled = holdings_df[
                ["symbol", "short_name", "quantity", "avg_buy_price", "price_live", "market_value", "unrealized_pnl"]
            ].sort_values("symbol").style.format(
                {
                    "avg_buy_price": fmt_currency,
                    "price_live": fmt_currency,
                    "market_value": fmt_currency,
                    "unrealized_pnl": fmt_currency,
                }
            )
            st.dataframe(holdings_styled, width="stretch", hide_index=True)

    with right:
        st.markdown("**Allocation**", unsafe_allow_html=True)
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
            st.plotly_chart(fig, width="stretch")

    st.markdown("**Positions**", unsafe_allow_html=True)
    positions_df = holdings_df[holdings_df["is_position"]] if not holdings_df.empty else holdings_df
    if positions_df.empty:
        st.info("No open positions right now — positions open when you buy a stock and expire shortly after.")
    else:
        positions_styled = positions_df[
            ["symbol", "short_name", "quantity", "avg_buy_price", "price_live", "market_value", "unrealized_pnl"]
        ].sort_values("symbol").style.format(
            {
                "avg_buy_price": fmt_currency,
                "price_live": fmt_currency,
                "market_value": fmt_currency,
                "unrealized_pnl": fmt_currency,
            }
        )
        st.dataframe(positions_styled, width="stretch", hide_index=True)

    st.divider()
    with st.expander("Danger zone"):
        st.caption(
            f"Delete portfolio '{portfolio.get('name')}' — this permanently removes the "
            "portfolio together with its holdings and transaction history. This cannot be undone."
        )
        confirm_delete = st.checkbox("I understand this permanently deletes the portfolio")
        if st.button("Delete this portfolio", disabled=not confirm_delete):
            st.session_state["confirm_delete_pending"] = True
            st.rerun()

    if st.session_state.get("confirm_delete_pending") and not st.session_state.get("pending_order"):
        delete_portfolio_dialog(client, selected_portfolio_id, portfolio.get("name", ""))


def main() -> None:
    """Streamlit page entrypoint."""
    ctx = shared.require_context()
    st.markdown(
        hero_html(
            "Portfolio Quant Dashboard",
            "Track, trade and analyse your portfolio with live market data.",
        ),
        unsafe_allow_html=True,
    )
    render(ctx)
