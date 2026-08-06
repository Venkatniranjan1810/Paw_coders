"""Application configuration pulled from environment variables and backend/.env.

Values come from (in precedence order):
  1. Real environment variables already set in the shell.
  2. The ``backend/.env`` file (see ``backend/.env.example``).

The `.env` file is gitignored, so credentials can live there safely.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_FILE)


class Settings:
    """Database and app settings (env/.env-overridable)."""

    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: int = int(os.getenv("DB_PORT", "3306"))
    DB_USER: str = os.getenv("DB_USER", "root")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")
    DB_NAME: str = os.getenv("DB_NAME", "portfolio_db")
    PRICE_REFRESH_INTERVAL_SECONDS: int = int(os.getenv("PRICE_REFRESH_INTERVAL_SECONDS", "120"))
    ALERT_CHECK_INTERVAL_SECONDS: int = int(os.getenv("ALERT_CHECK_INTERVAL_SECONDS", "3600"))
    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM: str = os.getenv("SMTP_FROM", "")


settings = Settings()
