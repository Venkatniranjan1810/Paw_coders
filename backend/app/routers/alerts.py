"""Alert API routes."""
from typing import Annotated, Optional

from app.exceptions import NotFoundError
from app.models import alerts as alerts_model
from app.models import user as user_model
from app.schemas.alerts import (
    AlertsListResponse,
    CheckResult,
    ReadResult,
)
from app.services import alerts as alerts_service
from fastapi import APIRouter, Query

router = APIRouter(prefix="/alerts", tags=["Alerts"])


def _require_user(user_id: int) -> None:
    if user_model.get_user_by_id(user_id) is None:
        raise NotFoundError(f"User {user_id} not found")


@router.get(
    "",
    response_model=AlertsListResponse,
    summary="List a user's alerts with unread count and health scores",
)
def list_alerts(
    user_id: Annotated[int, Query(alias="userId")],
    portfolio_id: Annotated[Optional[int], Query(alias="portfolioId")] = None,
    unread_only: Annotated[bool, Query(alias="unreadOnly")] = False,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
):
    """Return the user's alert history, plus the unread count (for a badge) and
    each portfolio's current composite health score."""
    _require_user(user_id)
    alerts = alerts_model.list_alerts(
        user_id, portfolio_id=portfolio_id, unread_only=unread_only, limit=limit
    )
    unread = alerts_model.count_unread(user_id)
    health_scores = alerts_service.compute_health_scores(user_id)
    return {"alerts": alerts, "unread_count": unread, "health_scores": health_scores}


@router.post(
    "/check",
    response_model=CheckResult,
    summary="Run an alert check now for a user",
)
def run_alert_check(
    user_id: Annotated[int, Query(alias="userId")],
    send_email: Annotated[bool, Query(alias="sendEmail")] = False,
):
    """Recompute risk and health scores for every portfolio of the user, persist
    newly abnormal alerts and optionally email them.

    With ``sendEmail=true`` this also emails the user's currently-pending unread
    alerts when this run creates no new ones, so the manual button always sends
    the outstanding abnormalities.
    """
    _require_user(user_id)
    return alerts_service.run_alert_check(user_id, send_email=send_email, email_existing=send_email)


@router.post(
    "/{alert_id}/read",
    response_model=ReadResult,
    summary="Mark an alert as read",
)
def mark_alert_read(alert_id: int):
    """Acknowledge an alert so it no longer counts toward the unread badge.

    Idempotent: re-reading an already-read alert still succeeds.
    """
    if not alerts_model.mark_read(alert_id):
        if alerts_model.get_alert(alert_id) is None:
            raise NotFoundError(f"Alert {alert_id} not found")
    return {"alert_id": alert_id, "is_read": True}
