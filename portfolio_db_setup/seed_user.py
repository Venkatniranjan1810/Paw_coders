"""Seed the single application user.

Usage:
    python seed_user.py
    python seed_user.py --name "Jane Doe" --email jane@example.com --balance 100000
"""
import argparse
import logging
import sys

import mysql.connector

from db import connect_database

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

DEFAULT_NAME = "DemoUser"
DEFAULT_EMAIL = "demouser@example.com"
DEFAULT_BALANCE = 100000.00


def parse_args():
    """Read command line options."""
    parser = argparse.ArgumentParser(description="Seed the single application user.")
    parser.add_argument("--name", default=DEFAULT_NAME, help="User display name.")
    parser.add_argument("--email", default=DEFAULT_EMAIL, help="User email (unique).")
    parser.add_argument("--balance", type=float, default=DEFAULT_BALANCE, help="Starting cash balance.")
    return parser.parse_args()


def seed_user(connection, name, email, balance):
    """Insert the user if it doesn't already exist, otherwise update it.

    Uniqueness is keyed on email so re-running the script is idempotent.
    """
    query = """
        INSERT INTO users (user_name, email, acct_balance)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE
            user_name    = VALUES(user_name),
            acct_balance = VALUES(acct_balance)
    """
    cursor = connection.cursor()
    cursor.execute(query, (name, email, balance))
    connection.commit()
    cursor.close()


def main() -> int:
    """Entry point: ensure exactly one user exists."""
    args = parse_args()
    try:
        connection = connect_database()
    except mysql.connector.Error as exc:
        logging.error("Could not connect to database: %s", exc)
        return 1

    try:
        # Guard: only seed if the users table is empty (single-user system).
        cursor = connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        (count,) = cursor.fetchone()
        cursor.close()

        if count > 0:
            logging.info("Users table already has %d row(s); updating user %s.", count, args.email)
        else:
            logging.info("Seeding user %s (%s) with balance %.2f.", args.name, args.email, args.balance)

        seed_user(connection, args.name, args.email, args.balance)
        logging.info("Done.")
    except mysql.connector.Error as exc:
        logging.error("Database error while seeding user: %s", exc)
        return 1
    except Exception as exc:
        logging.error("Unexpected error while seeding user: %s", exc)
        return 1
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
