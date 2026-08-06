import mysql.connector
from db_config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER


def connect_server():
    """Open a MySQL server connection."""
    return mysql.connector.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD)


def connect_database():
    """Open a MySQL database connection."""
    return mysql.connector.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, database=DB_NAME)


def run_statements(connection, statements):
    """Run SQL statements in one transaction.

    On failure the transaction is rolled back and the exception re-raised.
    The cursor is always closed, even when a statement fails.
    """
    cursor = connection.cursor()
    try:
        for statement in statements:
            cursor.execute(statement)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()