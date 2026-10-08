from datetime import datetime, timezone
from sqlalchemy.orm import Session
from fastapi import status
from app.contractors.models import Contractor, ContractorAlert
from app.contractors.schemas import ContractorCreate, ContractorResponse, ContractorAlertResponse, SubmissionPairResponse
from app.auth.models import User, UserRole
from app.dump_points.models import DumpPoint
from app.dump_points.schemas import DumpPointResponse
import app.dump_points.service as dump_point_service
from app.check_ins.models import CheckIn, CheckInType
from app.check_ins.schemas import CheckInResponse
from app.core.security import get_password_hash, verify_password
from app.core.exceptions import MundusException, EntityNotFoundException, PermissionDeniedException


import uuid

def create_contractor_service(db: Session, data: ContractorCreate) -> ContractorResponse:
    # 1. Validate unique contractor name
    existing_contractor = db.query(Contractor).filter(Contractor.name == data.name.strip()).first()
    if existing_contractor:
        raise MundusException(
            message=f"A contractor with name '{data.name}' already exists.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # 2. Validate unique email
    existing_user = db.query(User).filter(User.email == data.email.strip().lower()).first()
    if existing_user:
        raise MundusException(
            message=f"An account with email '{data.email}' already exists.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # 3. Create contractor User
    contractor_user = User(
        email=data.email.strip().lower(),
        hashed_password=get_password_hash(data.password),
        full_name=data.name.strip(),
        role=UserRole.CONTRACTOR,
        is_active=True,
    )
    db.add(contractor_user)
    db.commit()
    db.refresh(contractor_user)

    # 4. Create Contractor record
    stipend_val = float(data.monthly_stipend or 0.0)
    contractor = Contractor(
        id=uuid.uuid4().hex,
        name=data.name.strip(),
        email=data.email.strip().lower(),
        user_id=contractor_user.id,
        monthly_stipend=stipend_val,
        bank_name=data.bank_name,
        bank_account_number=data.bank_account_number,
        bank_account_name=data.bank_account_name,
        bank_code=data.bank_code,
    )

    if data.bank_account_number and data.bank_code:
        from app.payouts.bachs_client import bachs_client
        dest = bachs_client.create_destination(
            account_number=data.bank_account_number,
            bank_code=data.bank_code,
            preferred_name=data.bank_account_name or data.name,
        )
        contractor.payment_provider_recipient_id = dest.get("id")
        contractor.bank_name = dest.get("bank_name") or data.bank_name
        contractor.bank_account_name = dest.get("account_name") or data.bank_account_name
        contractor.payment_provider_metadata = dest

    db.add(contractor)
    db.commit()
    db.refresh(contractor)

    is_ready = bool(contractor.payment_provider_recipient_id and contractor.monthly_stipend > 0)
    return ContractorResponse(
        id=contractor.id,
        name=contractor.name,
        email=contractor.email,
        monthly_stipend=contractor.monthly_stipend,
        bank_name=contractor.bank_name,
        bank_account_number=contractor.bank_account_number,
        bank_account_name=contractor.bank_account_name,
        bank_code=contractor.bank_code,
        payment_provider_recipient_id=contractor.payment_provider_recipient_id,
        is_payout_ready=is_ready,
        site_count=0,
        overdue=0,
        critical=0,
        on_schedule=0,
        created_at=contractor.created_at,
    )


def list_contractors_service(
    db: Session,
    q: str | None = None,
    status_filter: str | None = None,
    needs_attention: bool = False,
    limit: int = 10,
    offset: int = 0,
    current_user: User | None = None,
    return_total: bool = False,
) -> list[ContractorResponse] | tuple[list[ContractorResponse], int]:
    query = db.query(Contractor)
    if current_user and current_user.role == UserRole.CONTRACTOR:
        query = query.filter(Contractor.user_id == current_user.id)
    contractors = query.all()
    all_sites = db.query(DumpPoint).all()
    now = datetime.now(timezone.utc)

    # Build contractor metrics lookup
    contractor_sites_map: dict[str, list[DumpPoint]] = {c.id: [] for c in contractors}

    for site in all_sites:
        if site.assigned_contractor_id and site.assigned_contractor_id in contractor_sites_map:
            contractor_sites_map[site.assigned_contractor_id].append(site)

    results = []
    for c in contractors:
        sites = contractor_sites_map[c.id]
        site_count = len(sites)
        overdue_count = 0
        critical_count = 0

        for site in sites:
            if site.last_clearance_timestamp:
                last_ts = site.last_clearance_timestamp
                if last_ts.tzinfo is None:
                    last_ts = last_ts.replace(tzinfo=timezone.utc)
                diff_days = (now - last_ts).total_seconds() / 86400.0
                if diff_days > 10.0:
                    critical_count += 1
                elif diff_days >= site.interval_days:
                    overdue_count += 1
            else:
                critical_count += 1

        on_schedule_count = max(0, site_count - overdue_count - critical_count)

        # Apply search query filter
        if q:
            query = q.lower()
            if not (query in c.name.lower() or query in c.email.lower()):
                continue

        # Apply status filter
        if status_filter and status_filter.lower() not in ("all", ""):
            sf = status_filter.lower()
            if sf == "critical" and critical_count == 0:
                continue
            elif sf == "overdue" and overdue_count == 0:
                continue
            elif sf == "on_schedule" and on_schedule_count == 0:
                continue

        # needs_attention=true means at least one overdue or critical site
        if needs_attention and (overdue_count + critical_count) == 0:
            continue

        is_ready = bool(c.payment_provider_recipient_id and (c.monthly_stipend or 0) > 0)
        results.append(
            ContractorResponse(
                id=c.id,
                name=c.name,
                email=c.email,
                monthly_stipend=float(c.monthly_stipend or 0.0),
                bank_name=c.bank_name,
                bank_account_number=c.bank_account_number,
                bank_account_name=c.bank_account_name,
                bank_code=c.bank_code,
                payment_provider_recipient_id=c.payment_provider_recipient_id,
                is_payout_ready=is_ready,
                site_count=site_count,
                overdue=overdue_count,
                critical=critical_count,
                on_schedule=on_schedule_count,
                created_at=c.created_at,
            )
        )

    # Default sort: critical desc
    results.sort(key=lambda r: r.critical, reverse=True)
    if return_total:
        return results[offset: offset + limit], len(results)
    return results[offset: offset + limit]


def get_contractor_sites_service(db: Session, current_user: User) -> list[DumpPointResponse]:
    """Returns assigned sites for the contractor, sorted most overdue first."""
    return dump_point_service.list_dump_points(db, current_user)


def get_contractor_submissions_service(
    db: Session,
    current_user: User,
    site_id: str | None = None,
    status_filter: str | None = None,
    q: str | None = None,
    limit: int = 10,
    offset: int = 0,
    return_total: bool = False,
) -> list[SubmissionPairResponse] | tuple[list[SubmissionPairResponse], int]:
    """Groups contractor submissions into before/after clearance pairs by site and date."""
    from app.check_ins.models import CheckInStatus
    query = db.query(CheckIn).filter(CheckIn.user_id == current_user.id)
    if site_id:
        query = query.filter(CheckIn.site_id == site_id)

    check_ins = query.order_by(CheckIn.server_timestamp.desc()).all()

    # Group by site_id and day (YYYY-MM-DD)
    groups: dict[tuple[str, str], dict] = {}
    for ci in check_ins:
        date_str = ci.server_timestamp.strftime("%Y-%m-%d")
        key = (ci.site_id, date_str)
        if key not in groups:
            site_name = ci.site.name if ci.site else f"Site #{ci.site_id}"
            groups[key] = {
                "date": date_str,
                "site_id": ci.site_id,
                "site_name": site_name,
                "before": None,
                "after": None,
                "has_flag": False,
            }

        ci_dto = CheckInResponse.model_validate(ci)
        if ci.type == CheckInType.BEFORE and groups[key]["before"] is None:
            groups[key]["before"] = ci_dto
            # Check if this check-in itself was flagged
            if hasattr(ci, "status") and ci.status in (CheckInStatus.FLAGGED, CheckInStatus.LOCATION_MISMATCH):
                groups[key]["has_flag"] = True
        elif ci.type == CheckInType.AFTER and groups[key]["after"] is None:
            groups[key]["after"] = ci_dto

    results = []
    for (s_id, d_str), data in groups.items():
        # Map to frontend status enum: complete | pending | flagged
        if data["before"] and data["after"]:
            pair_status = "complete"
        elif data["has_flag"]:
            pair_status = "flagged"
        elif data["before"]:
            pair_status = "pending"  # after missing (was "in_progress")
        else:
            pair_status = "pending"

        # Apply site-name search
        if q and q.lower() not in data["site_name"].lower():
            continue

        sf = (status_filter or "").lower()
        if sf and sf != "all" and pair_status != sf:
            continue

        results.append(
            SubmissionPairResponse(
                date=data["date"],
                site_id=data["site_id"],
                site_name=data["site_name"],
                before=data["before"],
                after=data["after"],
                status=pair_status,
            )
        )

    results.sort(key=lambda x: x.date, reverse=True)
    if return_total:
        return results[offset: offset + limit], len(results)
    return results[offset: offset + limit]


def get_contractor_alerts_service(db: Session, current_user: User) -> list[ContractorAlertResponse]:
    # Find contractor assigned sites
    contractor = db.query(Contractor).filter(Contractor.user_id == current_user.id).first()
    if not contractor:
        return []
    assigned_site_ids = [s.id for s in db.query(DumpPoint).filter(DumpPoint.assigned_contractor_id == contractor.id).all()]
    if not assigned_site_ids:
        return []

    alerts = (
        db.query(ContractorAlert)
        .filter(ContractorAlert.site_id.in_(assigned_site_ids))
        .order_by(ContractorAlert.created_at.desc())
        .all()
    )

    results = []
    for a in alerts:
        site_name = a.site.name if a.site else None
        results.append(
            ContractorAlertResponse(
                id=a.id,
                site_id=a.site_id,
                site_name=site_name,
                message=a.message,
                is_seen=a.is_seen,
                created_at=a.created_at,
            )
        )
    return results


def mark_contractor_alert_seen_service(db: Session, site_id: str, current_user: User) -> dict:
    alerts = (
        db.query(ContractorAlert)
        .filter(ContractorAlert.site_id == site_id)
        .all()
    )
    for a in alerts:
        a.is_seen = True
    db.commit()
    return {"message": f"Alerts for site {site_id} marked as seen.", "site_id": site_id}


def change_user_password_service(db: Session, user_id: int, current_user: User, current_password: str | None, new_password: str) -> dict:
    if not new_password or len(new_password) < 6:
        raise MundusException(
            message="Password must be at least 6 characters long.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise EntityNotFoundException("User", user_id)

    # Ownership or agency role required
    if current_user.id != target_user.id and current_user.role != UserRole.AGENCY:
        raise PermissionDeniedException("You can only change your own password or require agency administrative privileges.")

    # If updating own password, verify current password if supplied
    if current_user.id == target_user.id and current_password:
        if not verify_password(current_password, target_user.hashed_password):
            raise MundusException(
                message="Incorrect current password.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

    target_user.hashed_password = get_password_hash(new_password)
    db.commit()
    return {"message": "Password updated successfully."}
