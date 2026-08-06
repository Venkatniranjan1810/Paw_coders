"""Tests for the centralized exception handling layer.

These exercise ``app/exceptions.py`` and ``app/handlers.py`` directly on a
minimal FastAPI app, so no database or backend routers are involved.
"""
import pytest
import mysql.connector
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.exceptions import (
    AppError,
    BadRequestError,
    ConflictError,
    DatabaseError,
    ForbiddenError,
    InternalError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)
from app.handlers import register_exception_handlers


# --- Exception hierarchy -----------------------------------------------------

@pytest.mark.parametrize(
    ("exc_class", "status_code", "code"),
    [
        (NotFoundError, 404, "not_found"),
        (BadRequestError, 400, "bad_request"),
        (UnauthorizedError, 401, "unauthorized"),
        (ForbiddenError, 403, "forbidden"),
        (ConflictError, 409, "conflict"),
        (ValidationError, 422, "validation_error"),
        (InternalError, 500, "internal_error"),
        (DatabaseError, 503, "database_error"),
    ],
)
def test_app_error_subclass_metadata(exc_class, status_code, code):
    error = exc_class("something failed")
    assert isinstance(error, AppError)
    assert error.status_code == status_code
    assert error.code == code
    assert error.detail == "something failed"
    assert str(error) == "something failed"


def test_app_error_can_override_defaults():
    error = NotFoundError("custom", status_code=410, code="gone")
    assert error.status_code == 410
    assert error.code == "gone"


# --- Handlers via a minimal app ---------------------------------------------

def _make_client():
    """Build a tiny app with our handlers plus one route per failure mode."""
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/ok")
    def ok():
        return {"status": "ok"}

    @app.get("/not-found")
    def not_found():
        raise NotFoundError("Stock 42 not found")

    @app.get("/bad-request")
    def bad_request():
        raise BadRequestError("Custom ranges require both startDate and endDate")

    @app.get("/http-exception")
    def http_exception():
        raise HTTPException(status_code=400, detail="legacy http error")

    @app.get("/validation")
    def validation(fail: int):
        return {"fail": fail}

    @app.get("/mysql")
    def mysql_error():
        raise mysql.connector.errors.ProgrammingError(msg="syntax error", errno=1064)

    @app.get("/boom")
    def boom():
        raise RuntimeError("secret internal detail")

    # ``raise_server_exceptions=False`` lets the outermost error middleware
    # (which owns the generic ``Exception`` handler) send its JSON 500 instead
    # of letting TestClient re-raise the original exception.
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(scope="module")
def client():
    with _make_client() as client:
        yield client


def test_health_route_still_works(client):
    response = client.get("/ok")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_not_found_returns_404_envelope(client):
    response = client.get("/not-found")
    assert response.status_code == 404
    body = response.json()
    assert body["detail"] == "Stock 42 not found"
    assert body["error"] == {"code": "not_found", "status_code": 404}


def test_bad_request_returns_400_envelope(client):
    response = client.get("/bad-request")
    assert response.status_code == 400
    body = response.json()
    assert body["detail"] == "Custom ranges require both startDate and endDate"
    assert body["error"]["code"] == "bad_request"


def test_plain_http_exception_uses_same_envelope(client):
    response = client.get("/http-exception")
    assert response.status_code == 400
    body = response.json()
    assert body["detail"] == "legacy http error"
    assert body["error"]["code"] == "http_error"


def test_validation_error_returns_422(client):
    response = client.get("/validation?fail=not-an-int")
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert isinstance(body["detail"], list)


def test_mysql_error_returns_503_without_driver_detail(client):
    response = client.get("/mysql")
    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "database_unavailable"
    assert "Database connection failed" in body["detail"]
    assert "syntax error" not in body["detail"]


def test_unhandled_exception_returns_500_without_leaking_internals(client):
    response = client.get("/boom")
    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "internal_error"
    assert body["detail"] == "Something went wrong"
    assert "secret internal detail" not in body["detail"]
