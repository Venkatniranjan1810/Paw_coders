"""Application-wide exception hierarchy.

Domain/HTTP exceptions live here so the API layer (``app/routers``), the data
layer (``app/models``, ``app/database.py``) and the services layer
(``app/services``) can raise consistent, machine-readable errors without
importing FastAPI. The centralized handlers in ``app/handlers.py`` translate
every ``AppError`` into the same JSON envelope:

    {"detail": "...", "error": {"code": "not_found", "status_code": 404}}

Usage::

    raise NotFoundError(f"Stock {stock_id} not found")

    except mysql.connector.Error as exc:
        raise DatabaseError("Could not reach the database") from exc
"""
from typing import Optional


class AppError(Exception):
    """Base class for all application errors.

    Each subclass carries a default HTTP ``status_code`` and a stable
    machine-readable ``code``. ``detail`` is safe to surface to API clients.
    """

    status_code = 500
    code = "app_error"

    def __init__(
        self,
        detail: str = "Something went wrong",
        *,
        status_code: Optional[int] = None,
        code: Optional[str] = None,
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code

    def __str__(self) -> str:
        return self.detail


class NotFoundError(AppError):
    """Requested resource does not exist (HTTP 404)."""

    status_code = 404
    code = "not_found"


class BadRequestError(AppError):
    """Request is malformed or violates business rules (HTTP 400)."""

    status_code = 400
    code = "bad_request"


class UnauthorizedError(AppError):
    """Authentication missing or failed (HTTP 401)."""

    status_code = 401
    code = "unauthorized"


class ForbiddenError(AppError):
    """Authenticated but not allowed to perform the action (HTTP 403)."""

    status_code = 403
    code = "forbidden"


class ConflictError(AppError):
    """Request conflicts with the current state (HTTP 409)."""

    status_code = 409
    code = "conflict"


class ValidationError(AppError):
    """Payload failed validation (HTTP 422)."""

    status_code = 422
    code = "validation_error"


class InternalError(AppError):
    """Unexpected internal failure (HTTP 500)."""

    status_code = 500
    code = "internal_error"


class ServiceUnavailableError(AppError):
    """Dependency (e.g. the database) is unavailable (HTTP 503)."""

    status_code = 503
    code = "service_unavailable"


class DatabaseError(AppError):
    """Database connectivity or query failure (HTTP 503).

    Distinct from ``ServiceUnavailableError`` so the data layer can be precise
    about *what* is unavailable without the caller needing to know.
    """

    status_code = 503
    code = "database_error"


class ExternalServiceError(AppError):
    """An upstream service (Yahoo Finance, SMTP, ...) failed (HTTP 502)."""

    status_code = 502
    code = "external_service_error"
