"""Centralized exception handlers and logging setup.

Every exception that escapes a route handler is funnelled through one of the
handlers below, which return a consistent JSON envelope:

    {"detail": ..., "error": {"code": "...", "status_code": ...}}

Keeping the ``detail`` field is important: the Streamlit frontend
(``frontend/api_client.py``) surfaces that field to the user, so it must always
be present.
"""
import logging

import mysql.connector
from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.exceptions import AppError, InternalError

logger = logging.getLogger("app.exceptions")


def configure_logging() -> None:
    """Idempotent logging configuration so errors always carry context."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )


def _payload(detail: object, *, code: str, status_code: int) -> dict:
    """Build the shared error envelope returned to API clients."""
    return {
        "detail": jsonable_encoder(detail),
        "error": {"code": code, "status_code": status_code},
    }


async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    """Domain errors (AppError subclasses) → their declared status code."""
    return JSONResponse(
        status_code=exc.status_code,
        content=_payload(exc.detail, code=exc.code, status_code=exc.status_code),
    )


async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    """Any remaining plain FastAPI HTTPExceptions → same envelope."""
    return JSONResponse(
        status_code=exc.status_code,
        content=_payload(exc.detail, code="http_error", status_code=exc.status_code),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Request payload/query validation failures (HTTP 422).

    Logged at WARNING level (they are usually client mistakes, not bugs) and
    returned in the same envelope, preserving FastAPI's structured errors list.
    """
    logger.warning(
        "Request validation failed on %s %s: %s",
        request.method,
        request.url.path,
        exc.errors(),
    )
    return JSONResponse(
        status_code=422,
        content=_payload(exc.errors(), code="validation_error", status_code=422),
    )


async def mysql_error_handler(_request: Request, exc: mysql.connector.Error) -> JSONResponse:
    """MySQL driver errors (connection refused, wrong credentials, ...) → 503.

    The full driver detail is logged server-side but the client only receives a
    generic message so internal details are not leaked.
    """
    logger.error("MySQL error: %s", exc)
    return JSONResponse(
        status_code=503,
        content=_payload(
            "Database connection failed",
            code="database_unavailable",
            status_code=503,
        ),
    )


async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last-resort handler for anything not already caught.

    Logs the full traceback server-side and returns a generic 500 so internal
    exception details never leak to the client.
    """
    logger.exception(
        "Unhandled exception on %s %s: %s",
        request.method,
        request.url.path,
        exc,
    )
    error = InternalError()
    return JSONResponse(
        status_code=error.status_code,
        content=_payload(error.detail, code=error.code, status_code=error.status_code),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach every application exception handler to a FastAPI app."""
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(mysql.connector.Error, mysql_error_handler)
    app.add_exception_handler(Exception, unexpected_error_handler)
