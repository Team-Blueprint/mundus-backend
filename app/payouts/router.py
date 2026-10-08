import csv
import io
import json
from fastapi import APIRouter, Depends, status, Query, Request, Response, Header
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth.deps import get_current_user, require_role
from app.auth.models import User, UserRole
from app.contractors.models import Contractor
from app.payouts.models import PayoutStatement, PayoutStatus
from app.payouts.schemas import (
    ContractorPayoutDetailsUpdate,
    ContractorPayoutDetailsResponse,
    PayoutStatementResponse,
    PayoutStatementListResponse,
    ContractorProgressiveEarningsResponse,
    PayoutApprovalRequest,
    PayoutBulkApprovalRequest,
    HeldClearanceItem,
    BankItemResponse,
    BankResolveRequest,
    BankResolveResponse,
)
import app.payouts.service as payout_service
import os
from fastapi.responses import HTMLResponse
from app.payouts.bachs_client import bachs_client
from app.core.exceptions import PermissionDeniedException, MundusException

router = APIRouter(tags=["Payments & Payouts"])


# ============================================================================
# 0. Agency Payments UI Dashboard
# ============================================================================

@router.get(
    "/agency/payments/ui",
    response_class=HTMLResponse,
    summary="Interactive Agency Payments UI Dashboard",
)
@router.get(
    "/payments",
    response_class=HTMLResponse,
    summary="Interactive Agency Payments UI Dashboard (shortcut)",
)
def agency_payments_ui():
    """Serves the interactive Agency Payments Dashboard UI for Mundus."""
    template_path = os.path.join(os.path.dirname(__file__), "..", "templates", "agency_payments.html")
    if os.path.exists(template_path):
        with open(template_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    root_preview = os.path.abspath(os.path.join(os.path.dirname(__file__), "../..", "agency_payments_preview.html"))
    if os.path.exists(root_preview):
        with open(root_preview, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h2>Agency Payments UI is available.</h2>", status_code=200)


# ============================================================================
# 1. Agency Payments Endpoints
# ============================================================================

@router.get(
    "/agency/payouts",
    response_model=PayoutStatementListResponse,
    status_code=status.HTTP_200_OK,
    summary="List monthly payout statements for agency review",
)
def list_agency_payouts(
    period: str | None = Query(None, description="Month period 'YYYY-MM' (e.g. 2026-10)"),
    status_filter: str | None = Query(None, alias="status", description="Filter by status: DRAFT, PENDING_APPROVAL, APPROVED, PROCESSING, SUCCESS, FAILED, ALL"),
    contractor_id: str | None = Query(None, description="Filter by contractor ID"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.AGENCY])),
):
    """Retrieve monthly payout statements table for the Agency Payments view."""
    return payout_service.list_payout_statements_service(
        db=db,
        period=period,
        status_filter=status_filter,
        contractor_id=contractor_id,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/agency/payouts/generate",
    response_model=list[PayoutStatementResponse],
    status_code=status.HTTP_200_OK,
    summary="Generate month-end payout statements for all contractors",
)
def generate_payout_statements(
    period: str | None = Query(None, description="Month period 'YYYY-MM' (defaults to current month)"),
    contractor_id: str | None = Query(None, description="Optional single contractor ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.AGENCY])),
):
    """Calculates verified clearances and generates immutable payout statement snapshots for the month."""
    return payout_service.generate_payout_statements_service(
        db=db,
        period=period,
        contractor_id=contractor_id,
        current_user=current_user,
    )


@router.post(
    "/agency/payouts/bulk-approve",
    status_code=status.HTTP_200_OK,
    summary="Bulk approve month-end payouts",
)
def bulk_approve_payouts(
    data: PayoutBulkApprovalRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.AGENCY])),
):
    """Bulk approves all pending payout statements for a period in one action."""
    return payout_service.bulk_approve_payout_statements_service(
        db=db,
        period=data.period,
        statement_ids=data.statement_ids,
        current_user=current_user,
        notes=data.notes,
    )


@router.get(
    "/agency/payouts/export",
    summary="Export monthly payout statements as CSV",
)
def export_payout_statements_csv(
    period: str | None = Query(None, description="Month period 'YYYY-MM'"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.AGENCY])),
):
    """Export payout statements to CSV for municipal auditing and accounting."""
    p_data = payout_service.list_payout_statements_service(db, period=period, limit=5000)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Reference",
        "Contractor Name",
        "Contractor Email",
        "Period",
        "Monthly Stipend (NGN)",
        "Expected Clearances",
        "Verified Clearances",
        "Held Clearances",
        "Payout Earned (NGN)",
        "Status",
        "Transfer Code",
        "Approved At",
    ])

    for s in p_data.statements:
        writer.writerow([
            s.unique_payout_reference,
            s.contractor_name or "",
            s.contractor_email or "",
            s.period,
            f"{s.monthly_stipend:.2f}",
            s.expected_clearances,
            s.verified_clearances,
            s.held_clearances,
            f"{s.calculated_payout_amount:.2f}",
            s.status.value,
            s.transfer_code or "",
            s.approved_at.isoformat() if s.approved_at else "",
        ])

    csv_content = output.getvalue()
    filename = f"mundus_payouts_{period or 'all'}.csv"
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get(
    "/agency/payouts/{id}",
    response_model=PayoutStatementResponse,
    status_code=status.HTTP_200_OK,
    summary="Get single payout statement detail and audit history",
)
def get_payout_statement_detail(
    id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.AGENCY])),
):
    """Inspect calculations, clearance breakdown, and provider transaction audit trail for a statement."""
    return payout_service.get_payout_statement_service(db, id)


@router.post(
    "/agency/payouts/{id}/approve",
    response_model=PayoutStatementResponse,
    status_code=status.HTTP_200_OK,
    summary="Approve monthly payout and initiate Bachs transfer (Idempotent)",
)
def approve_payout(
    id: str,
    body: PayoutApprovalRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.AGENCY])),
):
    """Approve payout statement. Idempotent: duplicate requests return existing record without duplicate transfers."""
    notes = body.notes if body else None
    return payout_service.approve_payout_statement_service(
        db=db,
        statement_id=id,
        current_user=current_user,
        notes=notes,
    )


@router.put(
    "/agency/contractors/{id}/payout-details",
    response_model=ContractorPayoutDetailsResponse,
    status_code=status.HTTP_200_OK,
    summary="Set contractor monthly stipend and bank payout details",
)
def update_contractor_payout_details(
    id: str,
    data: ContractorPayoutDetailsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.AGENCY])),
):
    """Configures stipend and bank details once; registers transfer recipient with Bachs payment provider."""
    return payout_service.update_contractor_payout_details_service(
        db=db,
        contractor_id=id,
        data=data,
        current_user=current_user,
    )
    """Export payout statements to CSV for municipal auditing and accounting."""
    p_data = payout_service.list_payout_statements_service(db, period=period, limit=5000)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Reference",
        "Contractor Name",
        "Contractor Email",
        "Period",
        "Monthly Stipend (NGN)",
        "Expected Clearances",
        "Verified Clearances",
        "Held Clearances",
        "Payout Earned (NGN)",
        "Status",
        "Transfer Code",
        "Approved At",
    ])

    for s in p_data.statements:
        writer.writerow([
            s.unique_payout_reference,
            s.contractor_name or "",
            s.contractor_email or "",
            s.period,
            f"{s.monthly_stipend:.2f}",
            s.expected_clearances,
            s.verified_clearances,
            s.held_clearances,
            f"{s.calculated_payout_amount:.2f}",
            s.status.value,
            s.transfer_code or "",
            s.approved_at.isoformat() if s.approved_at else "",
        ])

    csv_content = output.getvalue()
    filename = f"mundus_payouts_{period or 'all'}.csv"
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get(
    "/agency/payouts/{id}/receipt",
    summary="Downloadable payment receipt for completed payout",
)
def get_payout_receipt(
    id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generates structured payment receipt details for an approved or completed monthly payout."""
    statement = payout_service.get_payout_statement_service(db, id)

    # Permission check: Agency or the contractor themselves
    if current_user.role == UserRole.CONTRACTOR:
        c = db.query(Contractor).filter(Contractor.user_id == current_user.id).first()
        if not c or c.id != statement.contractor_id:
            raise PermissionDeniedException("You may only view receipts for your own payouts.")

    return {
        "receipt_id": f"RCT-{statement.unique_payout_reference}",
        "reference": statement.unique_payout_reference,
        "transfer_code": statement.transfer_code,
        "payment_provider": statement.payment_provider,
        "period": statement.period,
        "contractor": {
            "name": statement.contractor_name,
            "email": statement.contractor_email,
        },
        "amount_paid": statement.calculated_payout_amount,
        "currency": "NGN",
        "performance": {
            "expected_clearances": statement.expected_clearances,
            "verified_clearances": statement.verified_clearances,
            "held_clearances": statement.held_clearances,
            "stipend": statement.monthly_stipend,
        },
        "status": statement.status.value,
        "approved_at": statement.approved_at,
        "approved_by": statement.approved_by_name,
        "environment": "sandbox (demo - no real money moved)",
    }


# ============================================================================
# 2. Held Clearances Review Queue
# ============================================================================

@router.get(
    "/agency/clearances/held",
    response_model=list[HeldClearanceItem],
    status_code=status.HTTP_200_OK,
    summary="List visits placed on hold for agency review",
)
def list_held_clearances(
    period: str | None = Query(None, description="Month period 'YYYY-MM'"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.AGENCY])),
):
    """Retrieve visits that failed geofence or duplicate checks and are placed on hold."""
    return payout_service.list_held_clearances_service(db, period=period)


@router.post(
    "/agency/clearances/{site_id}/{date}/approve",
    status_code=status.HTTP_200_OK,
    summary="Approve/clear a held visit",
)
def approve_held_clearance(
    site_id: str,
    date: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.AGENCY])),
):
    """Agency clears a held visit, marking it valid so it contributes to verified count."""
    return payout_service.clear_held_clearance_service(db, site_id, date, current_user)


# ============================================================================
# 3. Contractor Progressive Earnings & Payouts Endpoints
# ============================================================================

@router.get(
    "/contractor/earnings",
    response_model=ContractorProgressiveEarningsResponse,
    status_code=status.HTTP_200_OK,
    summary="Contractor real-time progressive monthly earnings tracker",
)
def get_my_progressive_earnings(
    period: str | None = Query(None, description="Month period 'YYYY-MM' (defaults to current month)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.CONTRACTOR])),
):
    """Allows contractor to see verified clearances, held visits, and earned stipend progress."""
    contractor = db.query(Contractor).filter(Contractor.user_id == current_user.id).first()
    if not contractor:
        raise MundusException(
            message="No contractor profile associated with this account.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return payout_service.get_progressive_earnings_service(db, contractor.id, period=period)


@router.get(
    "/contractor/payouts",
    response_model=list[PayoutStatementResponse],
    status_code=status.HTTP_200_OK,
    summary="Contractor payout history",
)
def get_my_payout_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.CONTRACTOR])),
):
    """Contractor views historical payout statements and approval status."""
    contractor = db.query(Contractor).filter(Contractor.user_id == current_user.id).first()
    if not contractor:
        return []

    statements = (
        db.query(PayoutStatement)
        .filter(PayoutStatement.contractor_id == contractor.id)
        .order_by(PayoutStatement.period.desc())
        .all()
    )
    return [payout_service._statement_to_dto(s) for s in statements]


@router.get(
    "/contractor/payouts/{id}",
    response_model=PayoutStatementResponse,
    status_code=status.HTTP_200_OK,
    summary="Contractor view individual payout statement",
)
def get_my_payout_statement(
    id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.CONTRACTOR])),
):
    """Inspect individual payout statement for current contractor."""
    contractor = db.query(Contractor).filter(Contractor.user_id == current_user.id).first()
    if not contractor:
        raise PermissionDeniedException("No contractor profile found.")

    statement = db.query(PayoutStatement).filter(PayoutStatement.id == id).first()
    if not statement:
        raise MundusException(message="Statement not found", status_code=status.HTTP_404_NOT_FOUND)

    if statement.contractor_id != contractor.id:
        raise PermissionDeniedException("You do not have permission to view this statement.")

    return payout_service._statement_to_dto(statement)


# ============================================================================
# 4. Bank Reference & Resolution Endpoints
# ============================================================================

@router.get(
    "/payouts/banks",
    response_model=list[BankItemResponse],
    status_code=status.HTTP_200_OK,
    summary="List supported Nigerian banks for payout registration",
)
def list_banks():
    """Returns supported Nigerian banks (names and codes) for agency bank configuration."""
    return bachs_client.list_banks(country="NG")


@router.post(
    "/payouts/resolve-account",
    response_model=BankResolveResponse,
    status_code=status.HTTP_200_OK,
    summary="Resolve bank account number and bank code to verified account name",
)
def resolve_bank_account(data: BankResolveRequest):
    """Looks up NUBAN bank account with Bachs to retrieve official account name."""
    res = bachs_client.resolve_bank_account(data.account_number, data.bank_code)
    return BankResolveResponse(**res)


# ============================================================================
# 5. Bachs Payment Provider Webhook Endpoint
# ============================================================================

@router.post(
    "/payouts/webhooks/bachs",
    status_code=status.HTTP_200_OK,
    summary="Bachs webhook delivery endpoint (Signed & Idempotent)",
)
async def bachs_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_bachs_signature_v2: str | None = Header(None, alias="X-Bachs-Signature-V2"),
    x_bachs_signature: str | None = Header(None, alias="X-Bachs-Signature"),
    x_bachs_timestamp: str | None = Header(None, alias="X-Bachs-Timestamp"),
):
    """Handles payout.paid and payout.failed events delivered by Bachs.

    Verifies HMAC-SHA256 signature, matches payout statement, and safely updates status.
    """
    raw_body = await request.body()

    # 1. Verify webhook signature
    is_valid = bachs_client.verify_webhook_signature(
        raw_body=raw_body,
        signature_v2=x_bachs_signature_v2,
        signature_v1=x_bachs_signature,
        timestamp_header=x_bachs_timestamp,
    )

    if not is_valid:
        raise MundusException(
            message="Invalid Bachs webhook signature.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    # 2. Parse event payload
    try:
        event = json.loads(raw_body.decode("utf-8"))
    except Exception:
        raise MundusException(
            message="Invalid JSON webhook payload.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # 3. Process event idempotently
    return payout_service.handle_bachs_webhook_service(db, event)
