import secrets
import urllib.parse
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from fastapi import status, HTTPException, BackgroundTasks
from app.reporters.models import Reporter, ReporterFlag, ReporterStatus
from app.reporters.schemas import (
    ReporterNominateRequest,
    ReporterResponse,
    ReporterApproveResponse,
    PublicReporterSiteResponse,
    ReporterFlagCreate,
    ReporterFlagResponse,
)
from app.dump_points.models import DumpPoint
from app.dump_points.schemas import DumpPointResponse
import app.dump_points.service as dump_point_service
from app.auth.models import User, UserRole
from app.contractors.models import ContractorAlert
from app.notifications.brevo import send_brevo_email, format_site_flagged_email
from app.notifications.service import send_push_notification, get_user_device_tokens
from app.core.exceptions import MundusException, EntityNotFoundException
from app.config import settings


def generate_whatsapp_link(phone: str, site_name: str, token: str) -> str:
    # Convert 080... to 23480...
    clean_phone = phone.strip()
    if clean_phone.startswith("0"):
        intl_phone = "234" + clean_phone[1:]
    else:
        intl_phone = clean_phone

    report_url = f"{settings.FRONTEND_ORIGIN}/r/{token}"
    raw_message = f"Mundus: you've been approved as reporter for {site_name}. Report a full site here: {report_url}"
    encoded_text = urllib.parse.quote(raw_message)
    return f"https://wa.me/{intl_phone}?text={encoded_text}"


def nominate_reporter_service(db: Session, data: ReporterNominateRequest) -> ReporterResponse:
    # 1. Verify site exists
    site = db.query(DumpPoint).filter(DumpPoint.id == data.site_id).first()
    if not site:
        raise EntityNotFoundException("DumpPoint", data.site_id)

    # 2. Check duplicate active reporter with same phone
    existing = (
        db.query(Reporter)
        .filter(
            Reporter.phone == data.phone,
            Reporter.status.in_([ReporterStatus.PENDING, ReporterStatus.APPROVED]),
        )
        .first()
    )
    if existing:
        raise MundusException(
            message=f"Phone {data.phone} already has an active or pending reporter registration.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # 3. Create reporter
    reporter = Reporter(
        name=data.name.strip(),
        phone=data.phone.strip(),
        site_id=data.site_id,
        contractor_id=data.contractor_id,
        status=ReporterStatus.PENDING,
    )
    db.add(reporter)
    db.commit()
    db.refresh(reporter)

    return ReporterResponse(
        id=reporter.id,
        name=reporter.name,
        phone=reporter.phone,
        site_id=reporter.site_id,
        site_name=site.name,
        contractor_id=reporter.contractor_id,
        status=reporter.status.value,
        token=None,
        rejection_reason=None,
        created_at=reporter.created_at,
        updated_at=reporter.updated_at,
        whatsapp_link=None,
    )


def list_reporters_service(
    db: Session,
    current_user: User,
    site_id: str | None = None,
    status_filter: str | None = None,
    q: str | None = None,
    limit: int = 10,
    offset: int = 0,
) -> list[ReporterResponse]:
    query = db.query(Reporter)
    if site_id:
        query = query.filter(Reporter.site_id == site_id)
    if status_filter and status_filter.lower() != "all":
        query = query.filter(Reporter.status == status_filter.lower())

    reporters = query.order_by(Reporter.created_at.desc()).all()

    results = []
    is_agency = current_user.role == UserRole.AGENCY

    for r in reporters:
        if q:
            term = q.lower()
            if term not in r.name.lower() and term not in r.phone:
                continue

        site_name = r.site.name if r.site else None
        token_val = r.token if is_agency else None
        wa_link = generate_whatsapp_link(r.phone, site_name or "Dump Point", r.token) if (is_agency and r.token) else None

        results.append(
            ReporterResponse(
                id=r.id,
                name=r.name,
                phone=r.phone,
                site_id=r.site_id,
                site_name=site_name,
                contractor_id=r.contractor_id,
                status=r.status.value,
                token=token_val,
                rejection_reason=r.rejection_reason,
                created_at=r.created_at,
                updated_at=r.updated_at,
                whatsapp_link=wa_link,
            )
        )
    return results[offset: offset + limit]


def approve_reporter_service(db: Session, reporter_id: int) -> ReporterApproveResponse:
    reporter = db.query(Reporter).filter(Reporter.id == reporter_id).first()
    if not reporter:
        raise EntityNotFoundException("Reporter", reporter_id)

    token = secrets.token_urlsafe(32)
    reporter.token = token
    reporter.status = ReporterStatus.APPROVED
    reporter.rejection_reason = None
    reporter.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(reporter)

    site_name = reporter.site.name if reporter.site else "Dump Point"
    wa_link = generate_whatsapp_link(reporter.phone, site_name, token)

    resp_dto = ReporterResponse(
        id=reporter.id,
        name=reporter.name,
        phone=reporter.phone,
        site_id=reporter.site_id,
        site_name=site_name,
        contractor_id=reporter.contractor_id,
        status=reporter.status.value,
        token=token,
        rejection_reason=None,
        created_at=reporter.created_at,
        updated_at=reporter.updated_at,
        whatsapp_link=wa_link,
    )

    return ReporterApproveResponse(
        reporter=resp_dto,
        token=token,
        whatsapp_link=wa_link,
    )


def reject_reporter_service(db: Session, reporter_id: int, reason: str | None = None) -> ReporterResponse:
    reporter = db.query(Reporter).filter(Reporter.id == reporter_id).first()
    if not reporter:
        raise EntityNotFoundException("Reporter", reporter_id)

    reporter.status = ReporterStatus.REJECTED
    reporter.rejection_reason = reason
    reporter.token = None
    reporter.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(reporter)

    site_name = reporter.site.name if reporter.site else None
    return ReporterResponse(
        id=reporter.id,
        name=reporter.name,
        phone=reporter.phone,
        site_id=reporter.site_id,
        site_name=site_name,
        contractor_id=reporter.contractor_id,
        status=reporter.status.value,
        token=None,
        rejection_reason=reporter.rejection_reason,
        created_at=reporter.created_at,
        updated_at=reporter.updated_at,
        whatsapp_link=None,
    )


def revoke_reporter_service(db: Session, reporter_id: int) -> ReporterResponse:
    reporter = db.query(Reporter).filter(Reporter.id == reporter_id).first()
    if not reporter:
        raise EntityNotFoundException("Reporter", reporter_id)

    reporter.status = ReporterStatus.REVOKED
    reporter.token = None
    reporter.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(reporter)

    site_name = reporter.site.name if reporter.site else None
    return ReporterResponse(
        id=reporter.id,
        name=reporter.name,
        phone=reporter.phone,
        site_id=reporter.site_id,
        site_name=site_name,
        contractor_id=reporter.contractor_id,
        status=reporter.status.value,
        token=None,
        rejection_reason=reporter.rejection_reason,
        created_at=reporter.created_at,
        updated_at=reporter.updated_at,
        whatsapp_link=None,
    )


def resolve_public_reporter_token(db: Session, token: str) -> PublicReporterSiteResponse:
    reporter = db.query(Reporter).filter(Reporter.token == token).first()
    if not reporter or reporter.status != ReporterStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reporter link is invalid, expired, or has been revoked.",
        )

    site = db.query(DumpPoint).filter(DumpPoint.id == reporter.site_id).first()
    if not site:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The associated dump point site no longer exists.",
        )

    site_flags = dump_point_service.get_site_flags(db, site.id)
    site_dto = DumpPointResponse.from_orm_computed(site, flags=site_flags)

    return PublicReporterSiteResponse(
        reporter={"name": reporter.name, "status": reporter.status.value},
        site=site_dto,
    )


def flag_site_full_service(
    db: Session,
    flag_in: ReporterFlagCreate,
    current_user: User | None = None,
    background_tasks: BackgroundTasks | None = None,
) -> ReporterFlagResponse:
    # 1. Verify dump point site exists
    site = db.query(DumpPoint).filter(DumpPoint.id == flag_in.site_id).first()
    if not site:
        raise EntityNotFoundException("DumpPoint", flag_in.site_id)

    reporter_community_id = None
    reporter_user_id = None
    reporter_name = "Community Reporter"

    # 2. Determine reporter identity via token or JWT
    if flag_in.reporter_token:
        reporter = db.query(Reporter).filter(Reporter.token == flag_in.reporter_token).first()
        if not reporter or reporter.status != ReporterStatus.APPROVED:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired reporter token.",
            )
        if reporter.site_id != flag_in.site_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reporter token is not assigned to this dump point site.",
            )
        reporter_community_id = reporter.id
        reporter_name = reporter.name
    elif current_user:
        reporter_user_id = current_user.id
        reporter_name = current_user.full_name or current_user.email
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Reporter token or authorization credentials are required to flag a site.",
        )

    # 3. 12-hour rate limiting check (site-wide lock)
    now = datetime.now(timezone.utc)
    twelve_hours_ago = now - timedelta(hours=12)

    recent_flag = (
        db.query(ReporterFlag)
        .filter(
            ReporterFlag.site_id == flag_in.site_id,
            ReporterFlag.timestamp >= twelve_hours_ago,
        )
        .order_by(ReporterFlag.timestamp.desc())
        .first()
    )

    if recent_flag:
        flag_ts = recent_flag.timestamp
        if flag_ts.tzinfo is None:
            flag_ts = flag_ts.replace(tzinfo=timezone.utc)
        elapsed_seconds = (now - flag_ts).total_seconds()
        remaining_seconds = max(0, 12 * 3600 - elapsed_seconds)
        hours_left = max(1, int(round(remaining_seconds / 3600.0)))
        retry_str = f"{hours_left} hours" if hours_left > 1 else "1 hour"

        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"detail": "Already reported", "retry_in": retry_str},
        )

    # 4. Save reporter flag record
    db_flag = ReporterFlag(
        site_id=flag_in.site_id,
        reporter_id=reporter_user_id or reporter_community_id,
        reporter_community_id=reporter_community_id,
        reporter_name=reporter_name,
        timestamp=now,
        note=flag_in.note,
        photo_url=flag_in.photo_url,
    )

    db.add(db_flag)

    # 5. Create Contractor alert banner
    alert_msg = f"{site.name} reported full by {reporter_name}"
    contractor_alert = ContractorAlert(
        site_id=site.id,
        contractor_id=site.assigned_contractor_id,
        message=alert_msg,
        is_seen=False,
    )
    db.add(contractor_alert)
    db.commit()
    db.refresh(db_flag)

    # 6. Dispatch async email and push notifications
    if site.assigned_contractor and site.assigned_contractor.user:
        contractor_user = site.assigned_contractor.user
        if contractor_user.email:
            subject, html_content, text_content = format_site_flagged_email(
                site_name=site.name,
                sector=site.sector,
                reporter_name=reporter_name,
                site_id=site.id,
                timestamp_str=now.strftime("%d %b %Y, %I:%M %p UTC"),
                photo_url=flag_in.photo_url,
            )
            if background_tasks:
                background_tasks.add_task(
                    send_brevo_email,
                    contractor_user.email,
                    contractor_user.full_name,
                    subject,
                    html_content,
                    text_content,
                )

                # FCM Push to contractor devices
                device_tokens = get_user_device_tokens(db, contractor_user.id)
            if device_tokens:
                background_tasks.add_task(
                    send_push_notification,
                    device_tokens,
                    {
                        "type": "site_flagged",
                        "site_id": str(site.id),
                        "site_name": site.name,
                        "at": now.isoformat(),
                        "photo_url": flag_in.photo_url or "",
                    },
                    f"⚠️ {site.name} Reported Full",
                    f"{reporter_name} flagged this site for immediate clearance.",
                )

    return ReporterFlagResponse(
        id=db_flag.id,
        site_id=db_flag.site_id,
        reporter_id=db_flag.reporter_id or db_flag.reporter_community_id,
        reporter_name=reporter_name,
        timestamp=db_flag.timestamp,
        note=db_flag.note,
        photo_url=db_flag.photo_url,
    )


def list_site_flags_service(db: Session, site_id: str) -> list[ReporterFlagResponse]:
    site = db.query(DumpPoint).filter(DumpPoint.id == site_id).first()
    if not site:
        raise EntityNotFoundException("DumpPoint", site_id)

    flags = (
        db.query(ReporterFlag)
        .filter(ReporterFlag.site_id == site_id)
        .order_by(ReporterFlag.timestamp.desc())
        .all()
    )

    results = []
    for f in flags:
        rep_name = f.reporter_name
        if not rep_name:
            if f.reporter:
                rep_name = f.reporter.full_name or f.reporter.email
            elif f.reporter_community:
                rep_name = f.reporter_community.name
        results.append(
            ReporterFlagResponse(
                id=f.id,
                site_id=f.site_id,
                reporter_id=f.reporter_id or f.reporter_community_id,
                reporter_name=rep_name,
                timestamp=f.timestamp,
                note=f.note,
            )
        )
    return results
