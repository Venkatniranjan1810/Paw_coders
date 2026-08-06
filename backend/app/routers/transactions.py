"""Transactions API routes."""
from datetime import date
from decimal import Decimal
from typing import Annotated, Optional

from app.exceptions import BadRequestError
from app.models import portfolio as portfolio_model
from app.models import transaction as transaction_model
from app.routers.utils import require_portfolio_exists
from app.schemas.transaction import Transaction, TransactionRangeResponse, TransType
from app.services.reports import build_transaction_pdf_report
from fastapi import APIRouter, Query, Response

router = APIRouter(prefix="/portfolios/{portfolio_id}/transactions", tags=["Transactions"])


@router.get("", response_model=list[Transaction], summary="Transaction history for a portfolio")
@require_portfolio_exists
def list_transactions(
    portfolio_id: int,
    trans_type: Annotated[Optional[TransType], Query(alias="transType")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """Return a portfolio's transactions, newest first."""
    type_value = trans_type.value if trans_type is not None else None
    return transaction_model.get_transactions(
        portfolio_id, trans_type=type_value, limit=limit, offset=offset
    )


@router.get(
    "/history",
    response_model=TransactionRangeResponse,
    summary="Transaction history for a chosen time interval or custom date range",
)
@require_portfolio_exists
def list_transactions_in_range(
    portfolio_id: int,
    interval: Annotated[Optional[str], Query(alias="interval")] = None,
    range_name: Annotated[Optional[str], Query(alias="range")] = None,
    start_date: Annotated[Optional[date], Query(alias="startDate")] = None,
    end_date: Annotated[Optional[date], Query(alias="endDate")] = None,
    trans_type: Annotated[Optional[TransType], Query(alias="transType")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """Return transactions for a portfolio within a bank-style interval."""

    selected_interval = interval or range_name or "last_month"
    if selected_interval == "custom" and (start_date is None or end_date is None):
        raise BadRequestError("Custom ranges require both startDate and endDate")

    if start_date is None and end_date is None:
        start_date, end_date = transaction_model.resolve_time_range(selected_interval)

    if start_date is not None and end_date is not None and start_date > end_date:
        raise BadRequestError("startDate must be on or before endDate")

    type_value = trans_type.value if trans_type is not None else None
    transactions = transaction_model.get_transactions_in_period(
        portfolio_id,
        start_date=start_date,
        end_date=end_date,
        trans_type=type_value,
        limit=limit,
        offset=offset,
    )

    total_amount = sum((Decimal(str(tx.get("amount") or 0)) for tx in transactions), Decimal("0"))

    return {
        "portfolio_id": portfolio_id,
        "range_label": _format_range_label(selected_interval, start_date, end_date),
        "start_date": start_date,
        "end_date": end_date,
        "total_count": len(transactions),
        "total_amount": total_amount,
        "transactions": transactions,
    }


@router.get(
    "/report",
    summary="Download transaction history as a PDF report",
    response_class=Response,
)
@require_portfolio_exists
def download_transactions_report(
    portfolio_id: int,
    interval: Annotated[Optional[str], Query(alias="interval")] = None,
    range_name: Annotated[Optional[str], Query(alias="range")] = None,
    start_date: Annotated[Optional[date], Query(alias="startDate")] = None,
    end_date: Annotated[Optional[date], Query(alias="endDate")] = None,
    trans_type: Annotated[Optional[TransType], Query(alias="transType")] = None,
):
    """Return a downloadable PDF report containing the selected transaction history."""

    selected_interval = interval or range_name or "last_month"
    if selected_interval == "custom" and (start_date is None or end_date is None):
        raise BadRequestError("Custom ranges require both startDate and endDate")

    if start_date is None and end_date is None:
        start_date, end_date = transaction_model.resolve_time_range(selected_interval)

    if start_date is not None and end_date is not None and start_date > end_date:
        raise BadRequestError("startDate must be on or before endDate")

    type_value = trans_type.value if trans_type is not None else None
    transactions = transaction_model.get_transactions_in_period(
        portfolio_id,
        start_date=start_date,
        end_date=end_date,
        trans_type=type_value,
        limit=500,
        offset=0,
    )

    pdf_bytes = build_transaction_pdf_report(
        portfolio_id=portfolio_id,
        transactions=transactions,
        range_label=_format_range_label(selected_interval, start_date, end_date),
        start_date=start_date,
        end_date=end_date,
        portfolio_name=portfolio_model.get_portfolio_by_id(portfolio_id).get("name"),
    )

    filename = f"transactions_{portfolio_id}_{selected_interval}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def _format_range_label(interval: str, start_date: Optional[date], end_date: Optional[date]) -> str:
    if interval == "custom" and start_date is not None and end_date is not None:
        return f"Custom ({start_date.isoformat()} to {end_date.isoformat()})"
    if interval == "last_week":
        return "Last week"
    if interval == "last_month":
        return "Last month"
    if interval == "last_6_months":
        return "Last 6 months"
    if interval == "last_1_year":
        return "Last 1 year"
    if interval == "last_5_years":
        return "Last 5 years"
    return interval.replace("_", " ").title()
