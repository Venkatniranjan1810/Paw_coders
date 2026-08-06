"""Watchlist page: track watched stocks and remove them."""
import pandas as pd
import streamlit as st

import shared
from api_client import APIError
from shared import fmt_currency, fmt_pct, live_ticker, spark_img


def render(ctx) -> None:
    client = ctx.client
    live_ticker(client)
    st.markdown(
        f'**Watchlist**'
        f'<span style="float:right">{spark_img(150, 38)}</span>',
        unsafe_allow_html=True,
    )

    try:
        watchlist = client.list_watchlist()
    except APIError as exc:
        watchlist = []
        st.error(str(exc))

    if not watchlist:
        st.info("Your watchlist is empty — add stocks from the Stocks tab.")
    else:
        watch_df = pd.DataFrame(watchlist)
        for col in ("current_price", "previous_close", "day_change", "day_change_pct"):
            watch_df[col] = pd.to_numeric(watch_df[col], errors="coerce")
        watch_styled = watch_df[
            ["symbol", "short_name", "sector", "current_price", "day_change", "day_change_pct"]
        ].style.format(
            {
                "current_price": fmt_currency,
                "day_change": fmt_currency,
                "day_change_pct": fmt_pct,
            }
        )
        st.dataframe(watch_styled, width="stretch", hide_index=True)

        rm_col, rm_btn_col = st.columns([3, 1])
        with rm_col:
            remove_symbol = st.selectbox(
                "Remove from watchlist", watch_df["symbol"].tolist(), key="watch_remove_symbol"
            )
        with rm_btn_col:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Remove", key="watch_remove_btn", width="stretch"):
                try:
                    row = watch_df[watch_df["symbol"] == remove_symbol].iloc[0]
                    client.remove_from_watchlist(int(row["stock_id"]))
                    st.success(f"Removed {remove_symbol} from the watchlist.")
                    st.rerun()
                except APIError as exc:
                    st.error(str(exc))


def main() -> None:
    """Streamlit page entrypoint."""
    ctx = shared.require_context()
    render(ctx)
