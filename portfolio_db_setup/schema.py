from db_config import DB_NAME

CREATE_DATABASE_SQL = f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"

TABLE_SQL = [
    """
    CREATE TABLE IF NOT EXISTS users (
        user_id BIGINT AUTO_INCREMENT PRIMARY KEY,
        user_name VARCHAR(100) NOT NULL,
        email VARCHAR(255) UNIQUE,
        bank_details VARCHAR(255),
        acct_balance NUMERIC(18,2) NOT NULL DEFAULT 0,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS stocks (
        stock_id BIGINT AUTO_INCREMENT PRIMARY KEY,
        symbol VARCHAR(20) NOT NULL UNIQUE,
        exchange VARCHAR(50),
        quote_type VARCHAR(50),
        short_name TEXT,
        long_name TEXT,
        currency VARCHAR(10),
        country VARCHAR(50),
        sector VARCHAR(100),
        industry VARCHAR(150),
        website TEXT,
        business_summary TEXT,
        market_cap BIGINT,
        shares_outstanding BIGINT,
        first_seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS portfolios (
        portfolio_id BIGINT AUTO_INCREMENT PRIMARY KEY,
        user_id BIGINT NOT NULL,
        name VARCHAR(100) NOT NULL DEFAULT 'My Portfolio',
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(user_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS watchlist (
        stock_id BIGINT NOT NULL PRIMARY KEY,
        added_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (stock_id) REFERENCES stocks(stock_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS holdings (
        portfolio_id BIGINT NOT NULL,
        stock_id BIGINT NOT NULL,
        quantity NUMERIC(18,6) NOT NULL DEFAULT 0,
        avg_buy_price NUMERIC(18,6),
        is_position BOOLEAN NOT NULL DEFAULT FALSE,
        position_expires_at TIMESTAMP NULL,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        PRIMARY KEY (portfolio_id, stock_id),
        FOREIGN KEY (portfolio_id) REFERENCES portfolios(portfolio_id),
        FOREIGN KEY (stock_id) REFERENCES stocks(stock_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS stock_prices (
        stock_id BIGINT NOT NULL,
        ts TIMESTAMP NOT NULL,
        `interval` VARCHAR(10) NOT NULL,
        `open` NUMERIC(18,6) NOT NULL,
        high NUMERIC(18,6) NOT NULL,
        low NUMERIC(18,6) NOT NULL,
        `close` NUMERIC(18,6) NOT NULL,
        adj_close NUMERIC(18,6),
        volume BIGINT,
        dividend NUMERIC(18,6),
        stock_split NUMERIC(18,6),
        source VARCHAR(50) DEFAULT 'yahoo_finance',
        ingested_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (stock_id, ts, `interval`),
        FOREIGN KEY (stock_id) REFERENCES stocks(stock_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS transactions (
        trans_id BIGINT AUTO_INCREMENT PRIMARY KEY,
        portfolio_id BIGINT NOT NULL,
        stock_id BIGINT,
        trans_type VARCHAR(20) NOT NULL,
        quantity NUMERIC(18,6),
        price NUMERIC(18,6),
        amount NUMERIC(18,2),
        trans_details VARCHAR(255),
        ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (portfolio_id) REFERENCES portfolios(portfolio_id),
        FOREIGN KEY (stock_id) REFERENCES stocks(stock_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS alerts (
        alert_id BIGINT AUTO_INCREMENT PRIMARY KEY,
        portfolio_id BIGINT,
        user_id BIGINT NOT NULL,
        category VARCHAR(50) NOT NULL,
        severity VARCHAR(20) NOT NULL,
        metric VARCHAR(50) NOT NULL,
        observed_value NUMERIC(18,6),
        threshold NUMERIC(18,6),
        message TEXT,
        is_read BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (portfolio_id) REFERENCES portfolios(portfolio_id),
        FOREIGN KEY (user_id) REFERENCES users(user_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS auto_trade_conditions (
        condition_id BIGINT AUTO_INCREMENT PRIMARY KEY,
        portfolio_id BIGINT NOT NULL,
        stock_id BIGINT NOT NULL,
        user_id BIGINT NOT NULL,
        action VARCHAR(10) NOT NULL,
        operator VARCHAR(5) NOT NULL,
        threshold_price NUMERIC(18,6) NOT NULL,
        quantity NUMERIC(18,6) NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'active',
        last_checked_at TIMESTAMP NULL,
        last_error TEXT,
        triggered_at TIMESTAMP NULL,
        trans_id BIGINT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        FOREIGN KEY (portfolio_id) REFERENCES portfolios(portfolio_id),
        FOREIGN KEY (stock_id) REFERENCES stocks(stock_id),
        FOREIGN KEY (user_id) REFERENCES users(user_id),
        FOREIGN KEY (trans_id) REFERENCES transactions(trans_id)
    )
    """,
]

INDEX_SQL = [
    "CREATE INDEX idx_prices_stock_ts ON stock_prices (stock_id, ts DESC)",
    "CREATE INDEX idx_txn_portfolio_ts ON transactions (portfolio_id, ts DESC)",
    "CREATE INDEX idx_holdings_stock ON holdings (stock_id)",
    "CREATE INDEX idx_stocks_symbol ON stocks (symbol)",
    "CREATE INDEX idx_alerts_user_ts ON alerts (user_id, created_at DESC)",
    "CREATE INDEX idx_autotrade_status_stock ON auto_trade_conditions (status, stock_id)",
]

ALTER_TABLE_SQL = [
    "ALTER TABLE holdings ADD COLUMN is_position BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE holdings ADD COLUMN position_expires_at TIMESTAMP NULL",
]