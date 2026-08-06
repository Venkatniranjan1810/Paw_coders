"""Trade page: buy and sell positions via a Buy/Sell toggle."""
import streamlit as st

import shared
import utils
from api_client import APIError
from shared import live_ticker, spark_img


def _render_buy_form(client, selected_portfolio_id: int) -> None:
    """Buy form: pick a stock from the catalog and specify a quantity."""
    stocks = client.list_stocks(limit=200)
    stock_lookup = {s["symbol"]: s for s in stocks}
    stock_symbols = sorted(stock_lookup.keys())
    trade_basket = list(st.session_state.trade_basket)

    with st.expander("Buy a position", expanded=True):
        if not stock_symbols:
            st.info("No stocks available.")
            return

        ordered_symbols = [s for s in trade_basket if s in stock_lookup] + [
            s for s in stock_symbols if s not in trade_basket
        ]
        buy_index = 0
        if "buy_symbol_pending" in st.session_state:
            pending = st.session_state.pop("buy_symbol_pending")
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

        buy_quantity = st.number_input(
            "Quantity (whole shares only)",
            min_value=1,
            step=1,
            value=1,
            format="%d",
        )
        if st.button("Buy stock", use_container_width=True):
            if selected_stock is None:
                st.error("Please select a valid stock.")
            elif quote_price is None:
                st.error("Live price unavailable for this stock — cannot place an order.")
            else:
                st.session_state["pending_order"] = {
                    "kind": "buy",
                    "portfolio_id": selected_portfolio_id,
                    "stock_id": int(selected_stock["stock_id"]),
                    "symbol": buy_symbol,
                    "quantity": int(buy_quantity),
                    "price": quote_price,
                }


def _render_sell_form(client, holdings_df, selected_portfolio_id: int) -> None:
    """Sell form: pick an owned position and specify a quantity to sell."""
    if holdings_df.empty:
        st.caption("You don't own any stocks yet — nothing to sell.")
        return

    with st.expander("Sell a position", expanded=True):
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
        if st.button("Sell stock", use_container_width=True):
            if sell_quote_price is None:
                st.error("Live price unavailable for this stock — cannot place an order.")
            else:
                sell_qty = max_quantity if sell_all else int(sell_quantity)
                st.session_state["pending_order"] = {
                    "kind": "sell",
                    "portfolio_id": selected_portfolio_id,
                    "stock_id": int(selected_holding["stock_id"]),
                    "symbol": sell_symbol,
                    "quantity": sell_qty,
                    "price": sell_quote_price,
                }


def render(ctx) -> None:
    client = ctx.client
    holdings_df = ctx.holdings_df
    selected_portfolio_id = ctx.selected_portfolio_id
    confirm_order_dialog = shared.confirm_order_dialog

    live_ticker(client)
    flash = st.session_state.pop("trade_flash", None)
    if flash:
        st.success(flash)

    st.markdown(
        f'**Trade**'
        f'<span style="float:right">{spark_img(150, 38)}</span>',
        unsafe_allow_html=True,
    )

    basket_click_pending = st.session_state.pop("basket_click_pending", None)
    if basket_click_pending:
        st.session_state["buy_symbol_pending"] = basket_click_pending

    trade_basket = list(st.session_state.trade_basket)
    if trade_basket:
        with st.expander(f"Trade basket ({len(trade_basket)} stock(s) from the Stocks tab)", expanded=True):
            st.caption("Click a stock to load it in the buy form below.")
            for sym in list(trade_basket):
                c1, c2 = st.columns([4, 1])
                with c1:
                    if st.button(f"**{sym}**", key=f"select_{sym}", width="stretch"):
                        st.session_state["buy_symbol_pending"] = sym
                        st.rerun()
                with c2:
                    if st.button("Remove", key=f"remove_{sym}", width="stretch"):
                        basket = list(st.session_state.trade_basket)
                        if sym in basket:
                            basket.remove(sym)
                        st.session_state.trade_basket = basket
                        st.rerun()

    mode = st.session_state.get("trade_mode", "buy")
    buy_col, sell_col = st.columns(2)
    with buy_col:
        if st.button("Buy", type="primary" if mode == "buy" else "secondary", width="stretch"):
            st.session_state.trade_mode = "buy"
            st.rerun()
    with sell_col:
        if st.button("Sell", type="primary" if mode == "sell" else "secondary", width="stretch"):
            st.session_state.trade_mode = "sell"
            st.rerun()

    if mode == "buy":
        _render_buy_form(client, selected_portfolio_id)
    else:
        _render_sell_form(client, holdings_df, selected_portfolio_id)

    if st.session_state.get("pending_order"):
        confirm_order_dialog(client)


def main() -> None:
    """Streamlit page entrypoint."""
    ctx = shared.require_context()
    render(ctx)
