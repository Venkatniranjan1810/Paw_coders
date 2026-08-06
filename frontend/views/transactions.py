"""Transactions page: filterable history with PDF export."""
from typing import Any

import pandas as pd
import streamlit as st

import shared
from api_client import APIError
from shared import fmt_currency, live_ticker, tx_stock_label


def render(ctx) -> None:
    client = ctx.client
    selected_portfolio_id = ctx.selected_portfolio_id

    live_ticker(client)
    st.markdown("**Transaction history**", unsafe_allow_html=True)

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
            "Download PDF report",
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
        mcol2.metric("Net flow", fmt_currency(tx_history.get("total_amount")))

        tx_df = pd.DataFrame(transactions)
        tx_df["ts"] = pd.to_datetime(tx_df["ts"])
        tx_display = tx_df.copy()
        tx_display["stock"] = tx_df.apply(tx_stock_label, axis=1)
        tx_display["price"] = pd.to_numeric(tx_display["price"], errors="coerce")
        tx_display["amount"] = pd.to_numeric(tx_display["amount"], errors="coerce")
        tx_styled = tx_display[
            ["trans_id", "trans_type", "stock", "quantity", "price", "amount", "trans_details", "ts"]
        ].style.format({"price": fmt_currency, "amount": fmt_currency})
        st.dataframe(tx_styled, width="stretch", hide_index=True)


def main() -> None:
    """Streamlit page entrypoint."""
    ctx = shared.require_context(show_controls=True)
    render(ctx)
