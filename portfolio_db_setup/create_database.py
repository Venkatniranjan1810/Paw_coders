import sys

import mysql.connector
from db import connect_database, connect_server, run_statements
from mysql.connector import errorcode
from schema import ALTER_TABLE_SQL, CREATE_DATABASE_SQL, INDEX_SQL, TABLE_SQL


def create_database():
    """Create the portfolio database."""
    connection = connect_server()
    try:
        run_statements(connection, [CREATE_DATABASE_SQL])
    finally:
        connection.close()


def create_tables():
    """Create portfolio tables and apply schema migrations if needed."""
    connection = connect_database()
    try:
        run_statements(connection, TABLE_SQL)
        cursor = connection.cursor()
        try:
            for statement in ALTER_TABLE_SQL:
                try:
                    cursor.execute(statement)
                except Exception as exc:
                    if getattr(exc, "errno", None) != errorcode.ER_DUP_FIELDNAME:
                        raise
            connection.commit()
        finally:
            cursor.close()
    finally:
        connection.close()


def create_indexes():
    """Create portfolio indexes."""
    connection = connect_database()
    try:
        cursor = connection.cursor()
        try:
            for statement in INDEX_SQL:
                try:
                    cursor.execute(statement)
                except Exception as exc:
                    if getattr(exc, "errno", None) != errorcode.ER_DUP_KEYNAME:
                        raise
            connection.commit()
        finally:
            cursor.close()
    finally:
        connection.close()


def setup_database():
    """Create database objects."""
    create_database()
    create_tables()
    create_indexes()


def main() -> int:
    """Run the full database setup, exiting non-zero on failure."""
    try:
        setup_database()
    except mysql.connector.Error as exc:
        print(f"Database error during setup: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Unexpected error during setup: {exc}", file=sys.stderr)
        return 1
    print("Database setup complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
