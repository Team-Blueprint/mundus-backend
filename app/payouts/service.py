import calendar
import math
import uuid
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from fastapi import status

from app.config import settings
from app.auth.models import User, UserRole
from app.dump_points.models import DumpPoint
from app.contractors.models import Contractor
from app.check_ins.models import CheckIn, CheckInType, CheckInStatus
from app.payouts.models import PayoutStatement, PayoutStatus, PayoutAuditLog, WalletTopUp
from app.payouts.schemas import (
    ContractorPayoutDetailsUpdate,
    ContractorPayoutDetailsResponse,
    PayoutStatementResponse,
    PayoutStatementListResponse,
    ContractorProgressiveEarningsResponse,
    SiteClearanceBreakdown,
    HeldClearanceItem,
    WalletTopUpRequest,
    WalletTopUpResponse,
)
from app.payouts.bachs_client import bachs_client
from app.core.exceptions import MundusException, EntityNotFoundException, PermissionDeniedException

logger = logging.getLogger("mundus.payouts")


def _parse_period(period_str: str | None = None) -> tuple[int, int, str, int]:
    """Parse period string 'YYYY-MM' or default to current UTC month.

    Returns (year, month, formatted_period_str, days_in_month).
    """
    now = datetime.now(timezone.utc)
    if not period_str:
        year, month = now.year, now.month
    else:
        try:
            parts = period_str.strip().split("-")
            year, month = int(parts[0]), int(parts[1])
            if not (1 <= month <= 12):
                raise ValueError("Month must be between 1 and 12")
        except Exception:
            raise MundusException(
                message=f"Invalid period format '{period_str}'. Expected 'YYYY-MM' (e.g. '2026-10').",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

    days_in_month = calendar.monthrange(year, month)[1]
    formatted = f"{year:04d}-{month:02d}"
    return year, month, formatted, days_in_month


def calculate_monthly_clearances(db: Session, contractor_id: str, period: str | None = None) -> dict:
    """Calculate expected, verified, held clearances and earned amount for a contractor for a month.

    Business Rules:
    - Expected clearances = sum of floor(days_in_month / site.interval_days) for all assigned sites.
    - Clearance verified only when visit:
      * has before photo
      * has after photo
      * passes geofence validation (distance <= radius, status != location_mismatch)
      * passes duplicate-photo checks
      * has not been flagged for review
    - Flagged visits placed on hold and do not contribute until cleared.
    - Payout formula: payout = min(stipend * (verified / expected), stipend)
    """
    contractor = db.query(Contractor).filter(Contractor.id == contractor_id).first()
    if not contractor:
        raise EntityNotFoundException("Contractor", contractor_id)

    year, month, period_str, days_in_month = _parse_period(period)

    month_start = datetime(year, month, 1, 0, 0, 0, tzinfo=timezone.utc)
    month_end = datetime(year, month, days_in_month, 23, 59, 59, 999999, tzinfo=timezone.utc)

    # 1. Fetch contractor's assigned dump points
    sites = db.query(DumpPoint).filter(DumpPoint.assigned_contractor_id == contractor.id).all()
    assigned_site_ids = [s.id for s in sites]

    # 2. Calculate expected clearances
    total_expected = 0
    site_breakdowns: list[SiteClearanceBreakdown] = []
    site_metrics: dict[str, dict] = {}

    for site in sites:
        interval = site.interval_days if site.interval_days and site.interval_days > 0 else 7
        site_expected = math.floor(days_in_month / interval)
        total_expected += site_expected

        site_metrics[site.id] = {
            "site_id": site.id,
            "site_name": site.name,
            "code": site.code,
            "interval_days": interval,
            "expected_clearances": site_expected,
            "verified_clearances": 0,
            "held_clearances": 0,
        }

    # 3. Query check-ins for the contractor's sites in the target month
    if assigned_site_ids:
        # Check-ins can be matched by site_id or user_id
        check_ins = (
            db.query(CheckIn)
            .filter(
                CheckIn.site_id.in_(assigned_site_ids),
                CheckIn.server_timestamp >= month_start,
                CheckIn.server_timestamp <= month_end,
            )
            .order_by(CheckIn.server_timestamp.asc())
            .all()
        )
    else:
        check_ins = []

    # 4. Group check-ins into daily site visits: (site_id, YYYY-MM-DD)
    visits: dict[tuple[str, str], dict] = {}
    for ci in check_ins:
        date_str = ci.server_timestamp.strftime("%Y-%m-%d")
        key = (ci.site_id, date_str)
        if key not in visits:
            visits[key] = {
                "site_id": ci.site_id,
                "date": date_str,
                "before": None,
                "after": None,
                "has_flag": False,
                "flags": [],
            }

        if ci.type == CheckInType.BEFORE and visits[key]["before"] is None:
            visits[key]["before"] = ci
        elif ci.type == CheckInType.AFTER and visits[key]["after"] is None:
            visits[key]["after"] = ci

        # Check for flags or geofence mismatch
        is_flagged = False
        if ci.status in (CheckInStatus.FLAGGED, CheckInStatus.LOCATION_MISMATCH):
            is_flagged = True
        if ci.distance_from_site_meters > settings.GEOFENCE_RADIUS_METERS:
            is_flagged = True
        if ci.flags and len(ci.flags) > 0:
            is_flagged = True

        if is_flagged:
            visits[key]["has_flag"] = True
            if ci.flags:
                visits[key]["flags"].extend(ci.flags)
            else:
                visits[key]["flags"].append(f"{ci.status.value}_check_in")

    # 5. Evaluate verified vs held clearances
    total_verified = 0
    total_held = 0

    for (s_id, d_str), visit_data in visits.items():
        has_before = bool(visit_data["before"] and visit_data["before"].photo_url)
        has_after = bool(visit_data["after"] and visit_data["after"].photo_url)

        # Full visit candidate
        if has_before and has_after:
            if not visit_data["has_flag"]:
                # Fully verified visit
                total_verified += 1
                if s_id in site_metrics:
                    site_metrics[s_id]["verified_clearances"] += 1
            else:
                # Visit placed on hold for agency review
                total_held += 1
                if s_id in site_metrics:
                    site_metrics[s_id]["held_clearances"] += 1
        elif visit_data["has_flag"]:
            # Even if only partial, flagged check-in is logged as held for review
            total_held += 1
            if s_id in site_metrics:
                site_metrics[s_id]["held_clearances"] += 1

    # 6. Apply payout formula:
    # payout = min(stipend * (verified / expected), stipend)
    stipend = float(contractor.monthly_stipend or 0.0)
    if total_expected > 0:
        ratio = total_verified / total_expected
        earned_amount = round(min(stipend * ratio, stipend), 2)
        progress_percent = round(min(ratio * 100.0, 100.0), 1)
    else:
        earned_amount = 0.0
        progress_percent = 0.0

    for sm in site_metrics.values():
        site_breakdowns.append(SiteClearanceBreakdown(**sm))

    return {
        "contractor_id": contractor.id,
        "contractor_name": contractor.name,
        "contractor_email": contractor.email,
        "period": period_str,
        "days_in_month": days_in_month,
        "monthly_stipend": stipend,
        "expected_clearances": total_expected,
        "verified_clearances": total_verified,
        "held_clearances": total_held,
        "earned_so_far": earned_amount,
        "progress_percent": progress_percent,
        "site_breakdown": site_breakdowns,
    }


def get_progressive_earnings_service(
    db: Session,
    contractor_id: str,
    period: str | None = None,
) -> ContractorProgressiveEarningsResponse:
    """Retrieve real-time progressive earnings for a contractor for a given month."""
    metrics = calculate_monthly_clearances(db, contractor_id, period)

    # Check if a payout statement already exists for this period
    statement = (
        db.query(PayoutStatement)
        .filter(
            PayoutStatement.contractor_id == contractor_id,
            PayoutStatement.period == metrics["period"],
        )
        .first()
    )

    statement_dto = PayoutStatementResponse.model_validate(statement) if statement else None

    return ContractorProgressiveEarningsResponse(
        contractor_id=metrics["contractor_id"],
        contractor_name=metrics["contractor_name"],
        period=metrics["period"],
        days_in_month=metrics["days_in_month"],
        monthly_stipend=metrics["monthly_stipend"],
        expected_clearances=metrics["expected_clearances"],
        verified_clearances=metrics["verified_clearances"],
        held_clearances=metrics["held_clearances"],
        earned_so_far=metrics["earned_so_far"],
        progress_percent=metrics["progress_percent"],
        sites_breakdown=metrics["site_breakdown"],
        payout_statement=statement_dto,
    )


def update_contractor_payout_details_service(
    db: Session,
    contractor_id: str,
    data: ContractorPayoutDetailsUpdate,
    current_user: User,
) -> ContractorPayoutDetailsResponse:
    """Update contractor stipend and bank details; registers Bachs payout destination recipient."""
    contractor = db.query(Contractor).filter(Contractor.id == contractor_id).first()
    if not contractor:
        raise EntityNotFoundException("Contractor", contractor_id)

    if data.monthly_stipend is not None:
        contractor.monthly_stipend = float(data.monthly_stipend)
    contractor.bank_account_number = data.bank_account_number.strip()
    contractor.bank_code = data.bank_code.strip()

    # Register destination with Bachs
    bachs_dest = bachs_client.create_destination(
        account_number=contractor.bank_account_number,
        bank_code=contractor.bank_code,
        preferred_name=data.bank_account_name or contractor.name,
    )

    contractor.payment_provider_recipient_id = bachs_dest.get("id")
    contractor.bank_name = bachs_dest.get("bank_name") or data.bank_name
    contractor.bank_account_name = bachs_dest.get("account_name") or data.bank_account_name or contractor.name
    contractor.payment_provider_metadata = bachs_dest

    db.commit()
    db.refresh(contractor)

    is_ready = bool(contractor.payment_provider_recipient_id and (contractor.monthly_stipend or 0) > 0)
    return ContractorPayoutDetailsResponse(
        contractor_id=contractor.id,
        name=contractor.name,
        email=contractor.email,
        monthly_stipend=float(contractor.monthly_stipend or 0.0),
        bank_name=contractor.bank_name,
        bank_account_number=contractor.bank_account_number,
        bank_account_name=contractor.bank_account_name,
        bank_code=contractor.bank_code,
        payment_provider_recipient_id=contractor.payment_provider_recipient_id,
        is_payout_ready=is_ready,
    )


def generate_payout_statements_service(
    db: Session,
    period: str | None = None,
    contractor_id: str | None = None,
    current_user: User | None = None,
) -> list[PayoutStatementResponse]:
    """Generate or update payout statements for contractors for a payment period.

    Ensures calculation snapshot is preserved for that month.
    """
    _, _, period_str, _ = _parse_period(period)

    query = db.query(Contractor)
    if contractor_id:
        query = query.filter(Contractor.id == contractor_id)
    contractors = query.all()

    statements: list[PayoutStatement] = []

    for c in contractors:
        # Calculate current earnings for period
        metrics = calculate_monthly_clearances(db, c.id, period_str)

        # Skip contractors with 0 stipend and 0 clearances unless explicitly requested
        if metrics["monthly_stipend"] <= 0 and metrics["expected_clearances"] <= 0 and not contractor_id:
            continue

        existing_stmt = (
            db.query(PayoutStatement)
            .filter(
                PayoutStatement.contractor_id == c.id,
                PayoutStatement.period == period_str,
            )
            .first()
        )

        if existing_stmt:
            # If already APPROVED, PROCESSING, or SUCCESS: MUST NOT modify historical calculation!
            if existing_stmt.status in (PayoutStatus.APPROVED, PayoutStatus.PROCESSING, PayoutStatus.SUCCESS):
                statements.append(existing_stmt)
                continue

            # Update DRAFT or PENDING_APPROVAL statement with latest month progress
            existing_stmt.monthly_stipend = metrics["monthly_stipend"]
            existing_stmt.expected_clearances = metrics["expected_clearances"]
            existing_stmt.verified_clearances = metrics["verified_clearances"]
            existing_stmt.held_clearances = metrics["held_clearances"]
            existing_stmt.calculated_payout_amount = metrics["earned_so_far"]
            existing_stmt.calculation_breakdown = {
                "site_breakdown": [b.model_dump() for b in metrics["site_breakdown"]],
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
            db.commit()
            db.refresh(existing_stmt)
            statements.append(existing_stmt)
        else:
            # Generate unique payout reference: MND-PO-YYYYMM-<CTR_PREFIX>-<RANDOM>
            clean_period = period_str.replace("-", "")
            ctr_token = c.id[:6].upper()
            unique_ref = f"MND-PO-{clean_period}-{ctr_token}-{uuid.uuid4().hex[:6].upper()}"

            new_stmt = PayoutStatement(
                id=uuid.uuid4().hex,
                contractor_id=c.id,
                period=period_str,
                monthly_stipend=metrics["monthly_stipend"],
                expected_clearances=metrics["expected_clearances"],
                verified_clearances=metrics["verified_clearances"],
                held_clearances=metrics["held_clearances"],
                calculated_payout_amount=metrics["earned_so_far"],
                status=PayoutStatus.PENDING_APPROVAL,
                unique_payout_reference=unique_ref,
                payment_provider="bachs",
                calculation_breakdown={
                    "site_breakdown": [b.model_dump() for b in metrics["site_breakdown"]],
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            db.add(new_stmt)
            db.commit()
            db.refresh(new_stmt)
            statements.append(new_stmt)

    return [_statement_to_dto(s) for s in statements]


def list_payout_statements_service(
    db: Session,
    period: str | None = None,
    status_filter: str | None = None,
    contractor_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> PayoutStatementListResponse:
    """List monthly payout statements with filtering and summary totals."""
    query = db.query(PayoutStatement)

    if period:
        _, _, period_str, _ = _parse_period(period)
        query = query.filter(PayoutStatement.period == period_str)

    if contractor_id:
        query = query.filter(PayoutStatement.contractor_id == contractor_id)

    if status_filter and status_filter.upper() != "ALL":
        try:
            p_status = PayoutStatus(status_filter.upper())
            query = query.filter(PayoutStatement.status == p_status)
        except ValueError:
            pass

    all_matched = query.order_by(PayoutStatement.created_at.desc()).all()
    total_count = len(all_matched)

    total_stipend = sum(s.monthly_stipend for s in all_matched)
    total_earned = sum(s.calculated_payout_amount for s in all_matched)
    total_paid = sum(
        s.calculated_payout_amount
        for s in all_matched
        if s.status in (PayoutStatus.SUCCESS, PayoutStatus.PROCESSING)
    )
    pending_count = sum(1 for s in all_matched if s.status == PayoutStatus.PENDING_APPROVAL)

    paginated = all_matched[offset: offset + limit]

    return PayoutStatementListResponse(
        period=period,
        total_stipend_pool=round(total_stipend, 2),
        total_earned_amount=round(total_earned, 2),
        total_paid_amount=round(total_paid, 2),
        pending_approval_count=pending_count,
        total_count=total_count,
        statements=[_statement_to_dto(s) for s in paginated],
    )


def get_payout_statement_service(db: Session, statement_id: str) -> PayoutStatementResponse:
    """Retrieve full audit details of a single payout statement."""
    statement = db.query(PayoutStatement).filter(PayoutStatement.id == statement_id).first()
    if not statement:
        raise EntityNotFoundException("PayoutStatement", statement_id)
    return _statement_to_dto(statement)


def approve_payout_statement_service(
    db: Session,
    statement_id: str,
    current_user: User,
    notes: str | None = None,
) -> PayoutStatementResponse:
    """Approve and release monthly payout through Bachs.

    Strict Idempotency Rules:
    - Never pays twice for the same payout statement.
    - If already APPROVED, PROCESSING, or SUCCESS, returns existing record.
    - Uses unique payout reference as Bachs transfer reference and Idempotency-Key.
    """
    statement = db.query(PayoutStatement).filter(PayoutStatement.id == statement_id).first()
    if not statement:
        raise EntityNotFoundException("PayoutStatement", statement_id)

    # 1. Idempotency Check: Already processed or in flight
    if statement.status in (PayoutStatus.APPROVED, PayoutStatus.PROCESSING, PayoutStatus.SUCCESS):
        logger.info(
            f"Idempotent approve: Statement {statement_id} is already in state {statement.status.value}"
        )
        return _statement_to_dto(statement)

    # 2. Contractor details validation
    contractor = statement.contractor
    if not contractor:
        raise MundusException(
            message="Contractor record associated with this payout statement was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    # Ensure recipient destination exists on Bachs
    if not contractor.payment_provider_recipient_id:
        if not contractor.bank_account_number or not contractor.bank_code:
            raise MundusException(
                message=f"Contractor '{contractor.name}' has no bank account configured. Please update bank details before approving payout.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        # Register recipient with Bachs
        dest = bachs_client.create_destination(
            account_number=contractor.bank_account_number,
            bank_code=contractor.bank_code,
            preferred_name=contractor.bank_account_name or contractor.name,
        )
        contractor.payment_provider_recipient_id = dest.get("id")
        contractor.bank_name = dest.get("bank_name") or contractor.bank_name
        db.commit()

    # 3. Calculated amount validation
    amount_to_pay = round(statement.calculated_payout_amount, 2)
    amount_str = f"{amount_to_pay:.2f}"

    # Handle zero payout amount
    if amount_to_pay <= 0:
        statement.status = PayoutStatus.SUCCESS
        statement.approved_by_id = current_user.id
        statement.approved_at = datetime.now(timezone.utc)
        statement.payment_provider_status = "completed"
        statement.audit_notes = notes or "Zero earned payout marked completed without transfer."
        db.commit()
        db.refresh(statement)
        return _statement_to_dto(statement)

    # 4. Platform balance check
    wallet = bachs_client.get_balance()
    platform_balance = float(wallet.get("balance", 0.0))
    if platform_balance < amount_to_pay:
        raise MundusException(
            message="insufficient_platform_balance",
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="insufficient_platform_balance",
        )

    # 5. Initiate transfer with Bachs
    logger.info(
        f"Initiating Bachs payout for statement {statement.id}: Amount {amount_str} NGN to {contractor.payment_provider_recipient_id}"
    )

    bachs_resp = bachs_client.initiate_payout(
        destination=contractor.payment_provider_recipient_id,
        amount=amount_str,
        reference=statement.unique_payout_reference,
        idempotency_key=statement.unique_payout_reference,
    )

    # If provider returned an error code
    if bachs_resp.get("_error_status") and bachs_resp.get("_error_status") >= 400:
        err_msg = bachs_resp.get("message") or bachs_resp.get("error") or "Payment provider rejected transfer"
        statement.status = PayoutStatus.FAILED
        statement.failure_reason = str(err_msg)
        statement.payment_provider_response = bachs_resp
        db.commit()
        db.refresh(statement)
        raise MundusException(
            message=f"Bachs transfer error: {err_msg}",
            status_code=status.HTTP_502_BAD_GATEWAY,
        )

    # 5. Transition status to PROCESSING (or SUCCESS in immediate sandbox resolution)
    transfer_code = bachs_resp.get("id") or bachs_resp.get("withdrawal_id")
    provider_status = bachs_resp.get("status", "pending")

    statement.approved_by_id = current_user.id
    statement.approved_at = datetime.now(timezone.utc)
    statement.transfer_code = transfer_code
    statement.payment_provider_status = provider_status
    statement.payment_provider_response = bachs_resp
    statement.audit_notes = notes

    # In sandbox test mode, mark as SUCCESS if provider returned pending/completed
    if settings.BACHS_TEST_MODE and provider_status in ("completed", "pending"):
        statement.status = PayoutStatus.SUCCESS
        statement.payment_provider_status = "completed"
    else:
        statement.status = PayoutStatus.PROCESSING

    db.commit()
    db.refresh(statement)

    # Record audit log
    audit_entry = PayoutAuditLog(
        statement_id=statement.id,
        actor_id=current_user.id,
        action="APPROVE_PAYOUT",
        from_status="PENDING_APPROVAL",
        to_status=statement.status.value,
        details={
            "amount": amount_str,
            "transfer_code": transfer_code,
            "provider": "bachs",
            "notes": notes,
        },
    )
    db.add(audit_entry)
    db.commit()

    return _statement_to_dto(statement)


def bulk_approve_payout_statements_service(
    db: Session,
    period: str,
    statement_ids: list[str] | None,
    current_user: User,
    notes: str | None = None,
) -> dict:
    """Bulk approve all eligible pending payout statements for a period."""
    query = db.query(PayoutStatement).filter(PayoutStatement.period == period)
    if statement_ids and len(statement_ids) > 0:
        query = query.filter(PayoutStatement.id.in_(statement_ids))
    else:
        query = query.filter(PayoutStatement.status == PayoutStatus.PENDING_APPROVAL)

    statements = query.all()
    approved_count = 0
    failed_count = 0
    errors = []

    for stmt in statements:
        try:
            approve_payout_statement_service(db, stmt.id, current_user, notes=notes)
            approved_count += 1
        except Exception as e:
            failed_count += 1
            errors.append({"statement_id": stmt.id, "error": str(e)})

    return {
        "period": period,
        "total_processed": len(statements),
        "approved_count": approved_count,
        "failed_count": failed_count,
        "errors": errors,
    }


def handle_bachs_webhook_service(db: Session, event: dict) -> dict:
    """Handle incoming Bachs webhook events (payout.paid, payout.failed).

    Idempotent: Duplicate webhook events do not alter already finalized payouts.
    """
    event_type = event.get("type", "")
    event_id = event.get("id", "")
    data = event.get("data") or {}

    reference = data.get("reference")
    withdrawal_id = data.get("withdrawal_id") or data.get("id")

    logger.info(
        f"Processing Bachs webhook: type={event_type}, id={event_id}, ref={reference}, withdrawal_id={withdrawal_id}"
    )

    # 1. Check if this is a wallet top-up event (TOPUP- reference or collection event)
    topup_record = None
    if reference and reference.startswith("TOPUP-"):
        topup_record = db.query(WalletTopUp).filter(WalletTopUp.reference == reference).first()
    elif event.get("data", {}).get("metadata", {}).get("purpose") == "mundus_agency_wallet_topup":
        ref = event.get("data", {}).get("reference")
        if ref:
            topup_record = db.query(WalletTopUp).filter(WalletTopUp.reference == ref).first()

    if topup_record:
        if event_type in ("collection.succeeded", "payment.success", "checkout.completed") or data.get("status") in ("successful", "completed", "paid"):
            topup_record.status = "completed"
            topup_record.provider_response = event
            db.commit()
            logger.info(f"Wallet top-up {topup_record.reference} marked COMPLETED via Bachs webhook.")
            return {"received": True, "action": "wallet_topup_completed", "reference": topup_record.reference}
        elif event_type in ("collection.failed", "payment.failed") or data.get("status") == "failed":
            topup_record.status = "failed"
            topup_record.provider_response = event
            db.commit()
            logger.info(f"Wallet top-up {topup_record.reference} marked FAILED via Bachs webhook.")
            return {"received": True, "action": "wallet_topup_failed", "reference": topup_record.reference}
        return {"received": True, "action": "wallet_topup_event_recorded", "reference": topup_record.reference}

    # 2. Locate statement by unique_payout_reference or transfer_code
    statement = None
    if reference:
        statement = db.query(PayoutStatement).filter(PayoutStatement.unique_payout_reference == reference).first()
    if not statement and withdrawal_id:
        statement = db.query(PayoutStatement).filter(PayoutStatement.transfer_code == withdrawal_id).first()

    if not statement:
        logger.warning(f"Webhook received for unknown payout reference '{reference}' / id '{withdrawal_id}'")
        return {"received": True, "action": "ignored_unknown_reference"}

    # Idempotency guard: If already in terminal SUCCESS state, duplicate webhook is a no-op
    if statement.status == PayoutStatus.SUCCESS and event_type == "payout.paid":
        return {"received": True, "action": "already_successful", "statement_id": statement.id}

    if event_type == "payout.paid" or data.get("status") == "completed":
        statement.status = PayoutStatus.SUCCESS
        statement.payment_provider_status = "completed"
        statement.payment_provider_response = event
        db.commit()
        logger.info(f"Payout {statement.unique_payout_reference} marked SUCCESS via webhook.")
        return {"received": True, "status": "SUCCESS", "statement_id": statement.id}

    elif event_type == "payout.failed" or data.get("status") == "failed":
        statement.status = PayoutStatus.FAILED
        statement.payment_provider_status = "failed"
        statement.failure_reason = data.get("failure_reason") or "Transfer delivery failed at destination bank"
        statement.payment_provider_response = event
        db.commit()
        logger.info(f"Payout {statement.unique_payout_reference} marked FAILED via webhook.")
        return {"received": True, "status": "FAILED", "statement_id": statement.id}

    return {"received": True, "action": "unhandled_event_type"}


def list_held_clearances_service(db: Session, period: str | None = None) -> list[HeldClearanceItem]:
    """Retrieve all flagged or location mismatch visits currently placed on hold."""
    year, month, period_str, days_in_month = _parse_period(period)
    month_start = datetime(year, month, 1, 0, 0, 0, tzinfo=timezone.utc)
    month_end = datetime(year, month, days_in_month, 23, 59, 59, 999999, tzinfo=timezone.utc)

    flagged_cis = (
        db.query(CheckIn)
        .filter(
            CheckIn.server_timestamp >= month_start,
            CheckIn.server_timestamp <= month_end,
            (CheckIn.status.in_([CheckInStatus.FLAGGED, CheckInStatus.LOCATION_MISMATCH]))
            | (CheckIn.distance_from_site_meters > settings.GEOFENCE_RADIUS_METERS),
        )
        .order_by(CheckIn.server_timestamp.desc())
        .all()
    )

    items: list[HeldClearanceItem] = []
    seen_keys = set()

    for ci in flagged_cis:
        date_str = ci.server_timestamp.strftime("%Y-%m-%d")
        key = (ci.site_id, date_str)
        if key in seen_keys:
            continue
        seen_keys.add(key)

        site = ci.site
        site_name = site.name if site else f"Site #{ci.site_id}"
        contractor_name = site.assigned_contractor.name if site and site.assigned_contractor else None
        contractor_id = site.assigned_contractor_id if site else None

        reason = ", ".join(ci.flags) if ci.flags else f"Status: {ci.status.value}"
        items.append(
            HeldClearanceItem(
                site_id=ci.site_id,
                site_name=site_name,
                date=date_str,
                contractor_id=contractor_id,
                contractor_name=contractor_name,
                before_check_in_id=ci.id if ci.type == CheckInType.BEFORE else None,
                after_check_in_id=ci.id if ci.type == CheckInType.AFTER else None,
                flags=ci.flags or [ci.status.value],
                reason=reason,
            )
        )

    return items


def clear_held_clearance_service(
    db: Session,
    site_id: str,
    date_str: str,
    current_user: User,
) -> dict:
    """Agency clears a held clearance, marking its check-ins as VALID so it contributes to verified count."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        raise MundusException(
            message=f"Invalid date format '{date_str}'. Expected YYYY-MM-DD.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    day_start = dt.replace(hour=0, minute=0, second=0, tzinfo=timezone.utc)
    day_end = dt.replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)

    check_ins = (
        db.query(CheckIn)
        .filter(
            CheckIn.site_id == site_id,
            CheckIn.server_timestamp >= day_start,
            CheckIn.server_timestamp <= day_end,
        )
        .all()
    )

    if not check_ins:
        raise MundusException(
            message=f"No check-ins found for site '{site_id}' on date '{date_str}'.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    for ci in check_ins:
        ci.status = CheckInStatus.VALID
        ci.flags = []

    db.commit()

    return {
        "message": f"Held clearance for site {site_id} on {date_str} cleared and approved by agency.",
        "site_id": site_id,
        "date": date_str,
        "cleared_by": current_user.email,
    }


def _statement_to_dto(s: PayoutStatement) -> PayoutStatementResponse:
    """Helper to convert PayoutStatement ORM to PayoutStatementResponse schema."""
    contractor_name = s.contractor.name if s.contractor else None
    contractor_email = s.contractor.email if s.contractor else None
    approved_by_name = s.approved_by.full_name or s.approved_by.email if s.approved_by else None

    return PayoutStatementResponse(
        id=s.id,
        contractor_id=s.contractor_id,
        contractor_name=contractor_name,
        contractor_email=contractor_email,
        period=s.period,
        monthly_stipend=s.monthly_stipend,
        expected_clearances=s.expected_clearances,
        verified_clearances=s.verified_clearances,
        held_clearances=s.held_clearances,
        calculated_payout_amount=s.calculated_payout_amount,
        status=s.status,
        unique_payout_reference=s.unique_payout_reference,
        transfer_code=s.transfer_code,
        approved_by_id=s.approved_by_id,
        approved_by_name=approved_by_name,
        approved_at=s.approved_at,
        payment_provider=s.payment_provider,
        payment_provider_status=s.payment_provider_status,
        failure_reason=s.failure_reason,
        calculation_breakdown=s.calculation_breakdown,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


def create_wallet_topup_session_service(
    db: Session,
    data: WalletTopUpRequest,
    current_user: User,
) -> WalletTopUpResponse:
    """Create a Bachs Checkout Session for agency wallet top-up."""
    if data.amount <= 0:
        raise MundusException(
            message="Top-up amount must be greater than zero.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    ref = f"TOPUP-AK-{uuid.uuid4().hex[:12].upper()}"
    metadata = {
        "initiated_by_user_id": current_user.id,
        "initiated_by_email": current_user.email,
        "purpose": "mundus_agency_wallet_topup",
    }

    session_data = bachs_client.create_checkout_session(
        amount=data.amount,
        reference=ref,
        customer_email=current_user.email,
        customer_name=current_user.full_name or "Agency Admin",
        redirect_url=data.redirect_url,
        metadata=metadata,
    )

    topup = WalletTopUp(
        id=uuid.uuid4().hex,
        reference=ref,
        amount=float(data.amount),
        currency="NGN",
        status="pending",
        checkout_url=session_data["checkout_url"],
        session_id=session_data.get("session_id"),
        initiated_by_id=current_user.id,
        provider_response=session_data,
    )
    db.add(topup)
    db.commit()
    db.refresh(topup)

    logger.info(f"Created wallet top-up session {ref} for NGN {data.amount:,.2f} by user {current_user.email}")
    return WalletTopUpResponse(
        checkout_url=topup.checkout_url,
        reference=topup.reference,
        amount=topup.amount,
        currency=topup.currency,
        session_id=topup.session_id,
        status=topup.status,
        created_at=topup.created_at,
    )


def list_wallet_topups_service(db: Session, limit: int = 20, offset: int = 0) -> list[WalletTopUpResponse]:
    """List recent wallet top-up sessions."""
    topups = (
        db.query(WalletTopUp)
        .order_by(WalletTopUp.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [
        WalletTopUpResponse(
            checkout_url=t.checkout_url,
            reference=t.reference,
            amount=t.amount,
            currency=t.currency,
            session_id=t.session_id,
            status=t.status,
            created_at=t.created_at,
        )
        for t in topups
    ]

