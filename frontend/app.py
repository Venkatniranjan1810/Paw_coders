"""Streamlit frontend for the QPMS FastAPI backend.

Run with: streamlit run frontend/app.py
"""
import streamlit as st

import shared
from theme import hero_html
from views import (
    alerts as alerts_page,
    analytics as analytics_page,
    dashboard as dashboard_page,
    stocks as stocks_page,
    trade as trade_page,
    transactions as transactions_page,
    watchlist as watchlist_page,
)

shared.setup_app()
ctx = shared.require_context(show_controls=True)

st.markdown(
    hero_html(
        "Portfolio Quant Dashboard",
        "Track, trade and analyse your portfolio with live market data.",
    ),
    unsafe_allow_html=True,
)

page_order = [
    ("Dashboard", dashboard_page.render),
    ("Trade", trade_page.render),
    ("Stocks", stocks_page.render),
    ("Watchlist", watchlist_page.render),
    ("Analytics", analytics_page.render),
    ("Alerts", alerts_page.render),
    ("Transactions", transactions_page.render),
]

tabs = st.tabs([name for name, _ in page_order])
for tab, (_, page_render) in zip(tabs, page_order):
    with tab:
        page_render(ctx)
