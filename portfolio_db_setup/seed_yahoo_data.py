import argparse
import logging
import sys

import mysql.connector

from create_database import setup_database
from db import connect_database
from yahoo_finance_loader import load_symbol
from stocks import TOP_50_US

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def parse_args():
    """Read command line options."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="+", default=TOP_50_US)
    parser.add_argument("--period", default="1y")
    parser.add_argument("--interval", default="1d")
    return parser.parse_args()


def seed_yahoo_data(symbols, period, interval, batch_size=3):
    """Seed stocks and prices from Yahoo Finance."""
    logging.info("Setting up database")
    setup_database()
    connection = connect_database()
    logging.info("Connected to database")
    try:
        for i, symbol in enumerate(symbols):
            logging.info("Loading symbol: %s (%d/%d)", symbol, i + 1, len(symbols))
            try:
                loaded_symbol, row_count = load_symbol(connection, symbol, period, interval)
                logging.info("Loaded %s: %d rows", loaded_symbol, row_count)
            except Exception as exc:
                logging.error("%s: failed (%s)", symbol.upper(), exc)

            if (i + 1) % batch_size == 0:
                connection.close()
                logging.info("Reconnecting to database after batch of %d symbols", batch_size)
                connection = connect_database()
    finally:
        connection.close()
        logging.info("Database connection closed")


def main() -> int:
    """Seed Yahoo Finance data, exiting non-zero if the setup/connection fails."""
    args = parse_args()
    logging.info("Seeding data for symbols: %s", ", ".join(args.symbols))
    try:
        seed_yahoo_data(args.symbols, args.period, args.interval)
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