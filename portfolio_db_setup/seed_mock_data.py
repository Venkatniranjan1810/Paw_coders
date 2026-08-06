import argparse
import logging
import random
import sys
from datetime import datetime, timedelta

import mysql.connector

from create_database import setup_database
from db import connect_database
from db_operations import upsert_stock
from stocks import TOP_50_US

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def parse_args():
    """Read command line options."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="+", default=TOP_50_US)
    parser.add_argument("--period", default="1y")
    parser.add_argument("--interval", default="1d")
    return parser.parse_args()


def generate_mock_stock_info(symbol):
    """Generate mock stock metadata."""
    sectors = ["Technology", "Finance", "Healthcare", "Energy", "Consumer", "Industrial"]
    industries = ["Software", "Banking", "Pharmaceuticals", "Oil & Gas", "Retail", "Manufacturing"]

    return {
        "shortName": f"{symbol} Inc",
        "longName": f"{symbol} Incorporated Company",
        "currency": "USD",
        "country": "US",
        "exchange": "NASDAQ",
        "sector": random.choice(sectors),
        "industry": random.choice(industries),
        "quoteType": "EQUITY",
        "marketCap": random.randint(100_000_000_000, 3_000_000_000_000),
        "sharesOutstanding": random.randint(1_000_000_000, 5_000_000_000),
        "website": f"https://www.{symbol.lower()}.com",
        "longBusinessSummary": f"{symbol} is a leading company in the {random.choice(industries)} industry.",
    }


def upsert_prices(connection, stock_id, num_days=252):
    """Generate and upsert mock price history."""
    cursor = connection.cursor()
    rows = []

    base_price = random.randint(50, 500)
    current_date = datetime.now().date() - timedelta(days=num_days)

    for _ in range(num_days):
        base_price = max(1, base_price + random.uniform(-2, 2))
        high = base_price + random.uniform(0, 1)
        low = base_price - random.uniform(0, 1)
        open_price = base_price - random.uniform(-0.5, 0.5)
        close_price = base_price
        volume = random.randint(1_000_000, 100_000_000)

        rows.append((
            stock_id,
            current_date.isoformat(),
            "1d",
            f"{open_price:.2f}",
            f"{high:.2f}",
            f"{low:.2f}",
            f"{close_price:.2f}",
            f"{close_price:.2f}",
            volume,
            None,
            None,
        ))
        current_date += timedelta(days=1)

    cursor.executemany(
        """
        INSERT INTO stock_prices (
            stock_id, ts, `interval`, `open`, high, low, `close`, adj_close,
            volume, dividend, stock_split
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            `open` = VALUES(`open`),
            high = VALUES(high),
            low = VALUES(low),
            `close` = VALUES(`close`),
            adj_close = VALUES(adj_close),
            volume = VALUES(volume),
            dividend = VALUES(dividend),
            stock_split = VALUES(stock_split)
        """,
        rows,
    )
    connection.commit()
    cursor.close()
    return len(rows)


def seed_mock_data(symbols, period, interval):
    """Seed stocks with mock data."""
    logging.info("Setting up database")
    setup_database()
    connection = connect_database()
    logging.info("Connected to database")
    try:
        for i, symbol in enumerate(symbols):
            logging.info("Loading symbol: %s (%d/%d)", symbol, i + 1, len(symbols))
            try:
                info = generate_mock_stock_info(symbol)
                stock_id = upsert_stock(connection, symbol, info)
                row_count = upsert_prices(connection, stock_id, num_days=252)
                logging.info("Loaded %s: %d rows", symbol.upper(), row_count)
            except Exception as exc:
                logging.error("%s: failed (%s)", symbol.upper(), exc)
    finally:
        connection.close()
        logging.info("Database connection closed")


def main() -> int:
    """Seed mock data, exiting non-zero if the setup/connection fails."""
    args = parse_args()
    logging.info("Seeding mock data for symbols: %s", ", ".join(args.symbols))
    try:
        seed_mock_data(args.symbols, args.period, args.interval)
    except mysql.connector.Error as exc:
        logging.error("Database error during seeding: %s", exc)
        return 1
    except Exception as exc:
        logging.error("Unexpected error during seeding: %s", exc)
        return 1
    logging.info("Seeding completed successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())
