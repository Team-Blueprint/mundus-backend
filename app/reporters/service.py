from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from fastapi import status
from app.reporters.models import ReporterFlag
from app.reporters.schemas import ReporterFlagCreate, ReporterFlagResponse
from app.dump_points.models import DumpPoint
from app.auth.models import User
from app.core.exceptions import MundusException, EntityNotFoundException


def flag_site_full_service(db: Session, flag_in: ReporterFlagCreate, current_user: User) -> ReporterFlagResponse:
    # 1. Verify site exists
    site = db.query(DumpPoint).filter(DumpPoint.id == flag_in.site_id).first()
    if not site:
        raise EntityNotFoundException("DumpPoint", flag_in.site_id)

    # 2. Check 12-hour rate limiting
    now = datetime.now(timezone.utc)
    twelve_hours_ago = now - timedelta(hours=12)

    recent_flag = (
        db.query(ReporterFlag)
        .filter(
            ReporterFlag.site_id == flag_in.site_id,
            ReporterFlag.timestamp >= twelve_hours_ago
        )
        .first()
    )

    if recent_flag:
        raise MundusException(
            message="This dump point has already been flagged as full within the past 12 hours.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # 3. Create reporter flag
    db_flag = ReporterFlag(
        site_id=flag_in.site_id,
        reporter_id=current_user.id,
        timestamp=now,
        note=flag_in.note,
    )
    db.add(db_flag)
    db.commit()
    db.refresh(db_flag)

    return ReporterFlagResponse.from_orm_custom(db_flag)


def list_site_flags_service(db: Session, site_id: int) -> list[ReporterFlagResponse]:
    site = db.query(DumpPoint).filter(DumpPoint.id == site_id).first()
    if not site:
        raise EntityNotFoundException("DumpPoint", site_id)

    flags = (
        db.query(ReporterFlag)
        .filter(ReporterFlag.site_id == site_id)
        .order_by(ReporterFlag.timestamp.desc())
        .all()
    )
    return [ReporterFlagResponse.from_orm_custom(f) for f in flags]

