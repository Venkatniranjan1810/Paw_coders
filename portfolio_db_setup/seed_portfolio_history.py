"""Seed a demo user/portfolio with realistic, backdated BUY/SELL history.

Loads real Yahoo Finance price history for a handful of symbols (plus a
benchmark like SPY), then simulates a sequence of trades spread across the
past `--period`, using the *actual* historical close price on each trade
date. This gives the P&L analytics endpoints (single-stock and portfolio-level
realized/unrealized P&L) real dispersion to work with instead of a single
same-day snapshot.

Usage:
    python seed_portfolio_history.py
    python seed_portfolio_history.py --email demouser@example.com --period 2y
    python seed_portfolio_history.py --reset   # wipe & rebuild this portfolio's history
"""
import argparse
import logging
import random
import sys
from decimal import ROUND_HALF_UP, Decimal

import mysql.connector

from create_database import setup_database
from db import connect_database
from yahoo_finance_loader import load_symbol

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

DEFAULT_SYMBOLS = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "JPM", "KO", "TSLA"]
BENCHMARK_SYMBOL = "SPY"
STARTING_BALANCE = Decimal("500000.00")
TRADES_PER_SYMBOL = 4          # BUY events per symbol, spread across the period
SELL_FRACTION_CHANCE = 0.5     # chance a symbol gets a partial SELL later on
INVEST_PER_BUY = (Decimal("1500"), Decimal("6000"))  # random $ spent per BUY


def parse_args():
    parser = argparse.ArgumentParser(description="Seed a demo portfolio with historical trades.")
    parser.add_argument("--email", default="demouser@example.com")
    parser.add_argument("--name", default="DemoUser")
    parser.add_argument("--portfolio-name", default="Demo Portfolio")
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--benchmark", default=BENCHMARK_SYMBOL)
    parser.add_argument("--period", default="2y", help="Yahoo history window, e.g. 1y, 2y")
    parser.add_argument("--interval", default="1d")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete existing holdings/transactions for this portfolio before reseeding",
    )
    return parser.parse_args()


# --- Setup: user, portfolio, price history ---------------------------------

def seed_user(connection, name, email, balance):
    cursor = connection.cursor(dictionary=True)
    cursor.execute(
        """
        INSERT INTO users (user_name, email, acct_balance)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE user_name = VALUES(user_name)
        """,
        (name, email, balance),
    )
    connection.commit()
    cursor.execute("SELECT user_id, acct_balance FROM users WHERE email = %s", (email,))
    row = cursor.fetchone()
    cursor.close()
    return row["user_id"]


def get_or_create_portfolio(connection, user_id, portfolio_name):
    cursor = connection.cursor(dictionary=True)
    cursor.execute(
        "SELECT portfolio_id FROM portfolios WHERE user_id = %s AND name = %s",
        (user_id, portfolio_name),
    )
    row = cursor.fetchone()
    if row:
        cursor.close()
        return row["portfolio_id"]

    cursor.execute(
        "INSERT INTO portfolios (user_id, name) VALUES (%s, %s)",
        (user_id, portfolio_name),
    )
    connection.commit()
    portfolio_id = cursor.lastrowid
    cursor.close()
    return portfolio_id


def reset_portfolio(connection, portfolio_id):
    cursor = connection.cursor()
    cursor.execute("DELETE FROM transactions WHERE portfolio_id = %s", (portfolio_id,))
    cursor.execute("DELETE FROM holdings WHERE portfolio_id = %s", (portfolio_id,))
    connection.commit()
    cursor.close()
    logging.info("Reset transactions/holdings for portfolio %s", portfolio_id)


def load_price_history(connection, symbols, period, interval):
    """Ensure symbols have stock + price rows; return {symbol: stock_id}."""
    stock_ids = {}
    for symbol in symbols:
        loaded_symbol, row_count = load_symbol(connection, symbol, period, interval)
        logging.info("Loaded %s: %d price rows", loaded_symbol, row_count)
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT stock_id FROM stocks WHERE symbol = %s", (loaded_symbol,))
        row = cursor.fetchone()
        cursor.close()
        if row is None or row_count == 0:
            logging.warning("Skipping %s: no price history available", loaded_symbol)
            continue
        stock_ids[loaded_symbol] = row["stock_id"]
    return stock_ids


def get_price_series(connection, stock_id, interval):
    """Return [(ts, close), ...] ordered oldest first."""
    cursor = connection.cursor(dictionary=True)
    cursor.execute(
        "SELECT ts, `close` FROM stock_prices WHERE stock_id = %s AND `interval` = %s ORDER BY ts ASC",
        (stock_id, interval),
    )
    rows = cursor.fetchall()
    cursor.close()
    return [(row["ts"], Decimal(str(row["close"]))) for row in rows]


# --- Trade simulation -------------------------------------------------------

def _round_qty(qty: Decimal) -> Decimal:
    return qty.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def simulate_trades(rng, symbol, price_series):
    """Build a chronological list of trade dicts for one symbol.

    Spreads TRADES_PER_SYMBOL buys evenly across the available price history,
    and — for roughly half the symbols — adds one later partial SELL so the
    portfolio has a mix of open and partially-realized positions.
    """
    if len(price_series) < TRADES_PER_SYMBOL * 5:
        logging.warning("Not enough history for %s to simulate trades; skipping", symbol)
        return []

    n = len(price_series)
    buy_indices = [int(n * frac) for frac in [i / TRADES_PER_SYMBOL for i in range(TRADES_PER_SYMBOL)]]
    buy_indices = sorted(set(min(idx, n - 1) for idx in buy_indices))

    trades = []
    held_qty = Decimal("0")
    for idx in buy_indices:
        ts, price = price_series[idx]
        if price <= 0:
            continue
        invest = Decimal(rng.uniform(float(INVEST_PER_BUY[0]), float(INVEST_PER_BUY[1])))
        qty = _round_qty(invest / price)
        if qty <= 0:
            continue
        held_qty += qty
        trades.append({"ts": ts, "trans_type": "BUY", "quantity": qty, "price": price})

    if trades and rng.random() < SELL_FRACTION_CHANCE:
        last_buy_idx = buy_indices[-1]
        sell_candidates = list(range(last_buy_idx + 1, n))
        if sell_candidates:
            sell_idx = rng.choice(sell_candidates)
            ts, price = price_series[sell_idx]
            sell_qty = _round_qty(held_qty * Decimal(rng.uniform(0.3, 0.6)))
            if 0 < sell_qty < held_qty and price > 0:
                trades.append({"ts": ts, "trans_type": "SELL", "quantity": sell_qty, "price": price})

    trades.sort(key=lambda t: t["ts"])
    return trades


def apply_trades(connection, portfolio_id, stock_id, symbol, trades):
    """Insert backdated transactions and return this symbol's final position."""
    cursor = connection.cursor()
    held_qty = Decimal("0")
    avg_price = Decimal("0")
    cash_flow = Decimal("0")

    for trade in trades:
        qty, price, ts = trade["quantity"], trade["price"], trade["ts"]
        amount = (qty * price).quantize(Decimal("0.01"))

        if trade["trans_type"] == "BUY":
            avg_price = (held_qty * avg_price + qty * price) / (held_qty + qty)
            held_qty += qty
            signed_amount = -amount
            cash_flow -= amount
            details = "Simulated buy order"
        else:  # SELL
            held_qty -= qty
            signed_amount = amount
            cash_flow += amount
            details = "Simulated sell order"

        cursor.execute(
            """
            INSERT INTO transactions
                (portfolio_id, stock_id, trans_type, quantity, price, amount, trans_details, ts)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (portfolio_id, stock_id, trade["trans_type"], qty, price, signed_amount, details, ts),
        )

    connection.commit()
    cursor.close()
    logging.info(
        "%s: %d trade(s) inserted, ending position %.4f shares @ avg $%.2f",
        symbol, len(trades), held_qty, avg_price,
    )
    return held_qty, avg_price, cash_flow


def upsert_holding(connection, portfolio_id, stock_id, quantity, avg_buy_price):
    if quantity <= 0:
        return
    cursor = connection.cursor()
    cursor.execute(
        """
        INSERT INTO holdings (portfolio_id, stock_id, quantity, avg_buy_price)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE quantity = VALUES(quantity), avg_buy_price = VALUES(avg_buy_price)
        """,
        (portfolio_id, stock_id, quantity, avg_buy_price),
    )
    connection.commit()
    cursor.close()


def update_balance(connection, user_id, starting_balance, total_cash_flow):
    """Set the user's cash balance to starting balance + net trade cash flow."""
    new_balance = starting_balance + total_cash_flow
    cursor = connection.cursor()
    cursor.execute("UPDATE users SET acct_balance = %s WHERE user_id = %s", (new_balance, user_id))
    connection.commit()
    cursor.close()
    logging.info("User %s cash balance set to $%.2f", user_id, new_balance)


# --- Entry point -------------------------------------------------------------

def main() -> int:
    args = parse_args()
    rng = random.Random(args.seed)

    logging.info("Ensuring database/tables exist")
    try:
        setup_database()
        connection = connect_database()
    except mysql.connector.Error as exc:
        logging.error("Database setup/connection failed: %s", exc)
        return 1

    try:
        user_id = seed_user(connection, args.name, args.email, STARTING_BALANCE)
        portfolio_id = get_or_create_portfolio(connection, user_id, args.portfolio_name)
        logging.info("User %s / portfolio %s ready", user_id, portfolio_id)

        if args.reset:
            reset_portfolio(connection, portfolio_id)

        all_symbols = list(dict.fromkeys([*args.symbols, args.benchmark]))
        stock_ids = load_price_history(connection, all_symbols, args.period, args.interval)

        total_cash_flow = Decimal("0")
        for symbol in args.symbols:
            stock_id = stock_ids.get(symbol)
            if stock_id is None:
                continue

            price_series = get_price_series(connection, stock_id, args.interval)
            trades = simulate_trades(rng, symbol, price_series)
            if not trades:
                continue

            held_qty, avg_price, cash_flow = apply_trades(connection, portfolio_id, stock_id, symbol, trades)
            upsert_holding(connection, portfolio_id, stock_id, held_qty, avg_price)
            total_cash_flow += cash_flow

        update_balance(connection, user_id, STARTING_BALANCE, total_cash_flow)

        logging.info(
            "Done. Portfolio %s is ready — benchmark '%s' is also seeded.",
            portfolio_id, args.benchmark,
        )
    except mysql.connector.Error as exc:
        logging.error("Database error while seeding portfolio history: %s", exc)
        return 1
    except Exception as exc:
        logging.error("Unexpected error while seeding portfolio history: %s", exc)
        return 1
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
