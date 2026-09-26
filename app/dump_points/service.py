from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from app.dump_points.models import DumpPoint
from app.dump_points.schemas import DumpPointCreate, DumpPointUpdate, DumpPointAssign, DumpPointResponse
from app.auth.models import User, UserRole
from app.core.exceptions import EntityNotFoundException, PermissionDeniedException


def get_site_flags(db: Session, site_id: int) -> list[str]:
    from app.check_ins.models import CheckIn, CheckInStatus
    from app.reporters.models import ReporterFlag

    flags = []

    # 1. Reporter flag within 12h
    twelve_hours_ago = datetime.now(timezone.utc) - timedelta(hours=12)
    recent_reporter_flag = (
        db.query(ReporterFlag)
        .filter(ReporterFlag.site_id == site_id, ReporterFlag.timestamp >= twelve_hours_ago)
        .first()
    )
    if recent_reporter_flag:
        flags.append("Reported full")

    # 2. Check-in flags (location mismatch or duplicate photo)
    recent_check_in = (
        db.query(CheckIn)
        .filter(CheckIn.site_id == site_id)
        .order_by(CheckIn.server_timestamp.desc())
        .first()
    )

    if recent_check_in:
        if recent_check_in.status == CheckInStatus.LOCATION_MISMATCH or recent_check_in.distance_from_site_meters > 100:
            dist = int(round(recent_check_in.distance_from_site_meters))
            flags.append(f"Location mismatch ({dist} m)")

        if recent_check_in.flags and any("duplicate" in str(f).lower() for f in recent_check_in.flags):
            flags.append("Duplicate photo")
        elif recent_check_in.status == CheckInStatus.FLAGGED:
            flags.append("Duplicate photo")

    return flags


def create_dump_point(db: Session, dump_point_in: DumpPointCreate) -> DumpPointResponse:
    db_obj = DumpPoint(
        name=dump_point_in.name,
        latitude=dump_point_in.latitude,
        longitude=dump_point_in.longitude,
        code=dump_point_in.code,
        sector=dump_point_in.sector,
        assigned_contractor_id=dump_point_in.assigned_contractor_id,
        assigned_supervisor_id=dump_point_in.assigned_supervisor_id,
        interval_days=dump_point_in.interval_days,
    )
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    site_flags = get_site_flags(db, db_obj.id)
    return DumpPointResponse.from_orm_computed(db_obj, flags=site_flags)


def list_dump_points(
    db: Session,
    current_user: User,
    status_filter: str | None = None,
    search_query: str | None = None,
) -> list[DumpPointResponse]:
    query = db.query(DumpPoint)
    if current_user.role == UserRole.SUPERVISOR:
        query = query.filter(DumpPoint.assigned_supervisor_id == current_user.id)

    dump_points = query.all()
    results = []
    for dp in dump_points:
        site_flags = get_site_flags(db, dp.id)
        resp = DumpPointResponse.from_orm_computed(dp, flags=site_flags)
        results.append(resp)

    # Filter by status if requested
    if status_filter and status_filter.lower() != "all":
        sf = status_filter.lower()
        if sf == "flagged":
            results = [r for r in results if len(r.flags) > 0]
        elif sf in ["critical", "overdue", "on_schedule"]:
            results = [r for r in results if r.status == sf]

    # Filter by search query if requested
    if search_query:
        q = search_query.lower()

        def matches(r: DumpPointResponse) -> bool:
            if q in r.name.lower():
                return True
            if r.code and q in r.code.lower():
                return True
            if r.sector and q in r.sector.lower():
                return True
            if r.assigned_contractor_name and q in r.assigned_contractor_name.lower():
                return True
            if r.assigned_supervisor_name and q in r.assigned_supervisor_name.lower():
                return True
            return False

        results = [r for r in results if matches(r)]

    # Sort by days_since_last_clearance descending
    results.sort(
        key=lambda r: r.days_since_last_clearance if r.days_since_last_clearance is not None else float("inf"),
        reverse=True,
    )
    return results


def get_dump_point_by_id(db: Session, dump_point_id: int, current_user: User = None) -> DumpPointResponse:
    db_obj = db.query(DumpPoint).filter(DumpPoint.id == dump_point_id).first()
    if not db_obj:
        raise EntityNotFoundException("DumpPoint", dump_point_id)

    if current_user and current_user.role == UserRole.SUPERVISOR:
        if db_obj.assigned_supervisor_id != current_user.id:
            raise PermissionDeniedException("Supervisors can only access their assigned dump points.")

    site_flags = get_site_flags(db, db_obj.id)
    return DumpPointResponse.from_orm_computed(db_obj, flags=site_flags)


def assign_supervisor(db: Session, dump_point_id: int, assign_data: DumpPointAssign) -> DumpPointResponse:
    db_obj = db.query(DumpPoint).filter(DumpPoint.id == dump_point_id).first()
    if not db_obj:
        raise EntityNotFoundException("DumpPoint", dump_point_id)

    if assign_data.assigned_supervisor_id is not None:
        db_obj.assigned_supervisor_id = assign_data.assigned_supervisor_id
    if assign_data.assigned_contractor_id is not None:
        db_obj.assigned_contractor_id = assign_data.assigned_contractor_id

    db.commit()
    db.refresh(db_obj)
    site_flags = get_site_flags(db, db_obj.id)
    return DumpPointResponse.from_orm_computed(db_obj, flags=site_flags)


def update_dump_point(db: Session, dump_point_id: int, update_data: DumpPointUpdate) -> DumpPointResponse:
    db_obj = db.query(DumpPoint).filter(DumpPoint.id == dump_point_id).first()
    if not db_obj:
        raise EntityNotFoundException("DumpPoint", dump_point_id)

    for field, value in update_data.model_dump(exclude_unset=True).items():
        setattr(db_obj, field, value)

    db.commit()
    db.refresh(db_obj)
    site_flags = get_site_flags(db, db_obj.id)
    return DumpPointResponse.from_orm_computed(db_obj, flags=site_flags)


def delete_dump_point(db: Session, dump_point_id: int) -> dict:
    db_obj = db.query(DumpPoint).filter(DumpPoint.id == dump_point_id).first()
    if not db_obj:
        raise EntityNotFoundException("DumpPoint", dump_point_id)

    from app.reporters.models import ReporterFlag, Reporter
    from app.check_ins.models import CheckIn
    from app.contractors.models import ContractorAlert

    # Clean up related records
    db.query(ReporterFlag).filter(ReporterFlag.site_id == dump_point_id).delete(synchronize_session=False)
    db.query(Reporter).filter(Reporter.site_id == dump_point_id).delete(synchronize_session=False)
    db.query(CheckIn).filter(CheckIn.site_id == dump_point_id).delete(synchronize_session=False)
    db.query(ContractorAlert).filter(ContractorAlert.site_id == dump_point_id).delete(synchronize_session=False)

    site_name = db_obj.name
    db.delete(db_obj)
    db.commit()
    return {"message": f"Dump point '{site_name}' deleted successfully.", "id": dump_point_id}



def get_site_history_timeline(db: Session, dump_point_id: int, current_user: User) -> list[dict]:
    # Verify site access
    get_dump_point_by_id(db, dump_point_id, current_user)

    from app.check_ins.models import CheckIn, CheckInType
    from app.reporters.models import ReporterFlag

    check_ins = db.query(CheckIn).filter(CheckIn.site_id == dump_point_id).order_by(CheckIn.server_timestamp.desc()).all()
    reporter_flags = db.query(ReporterFlag).filter(ReporterFlag.site_id == dump_point_id).order_by(ReporterFlag.timestamp.desc()).all()

    events = []

    for ci in check_ins:
        actor_name = ci.supervisor.full_name if ci.supervisor else "Supervisor"
        ts_iso = ci.server_timestamp.isoformat()
        photo_info = {
            "photo_url": ci.photo_url,
            "lat": ci.latitude,
            "lng": ci.longitude,
            "distance_m": round(ci.distance_from_site_meters, 1),
            "at": ts_iso,
        }

        if ci.type == CheckInType.BEFORE:
            events.append({
                "kind": "check_in",
                "at": ts_iso,
                "actor": actor_name,
                "note": "Before photo submitted",
                "before": photo_info,
                "after": None,
            })
        else:
            events.append({
                "kind": "check_in",
                "at": ts_iso,
                "actor": actor_name,
                "note": "After photo submitted",
                "before": None,
                "after": photo_info,
            })
            events.append({
                "kind": "clearance",
                "at": ts_iso,
                "actor": "system",
                "note": "Visit complete, counter reset",
            })

    for rf in reporter_flags:
        rep_actor = rf.reporter_name or "Community Reporter"
        events.append({
            "kind": "flag",
            "at": rf.timestamp.isoformat(),
            "actor": f"{rep_actor} (reporter)",
            "note": rf.note or "Site reported full",
        })

    events.sort(key=lambda e: e["at"], reverse=True)
    return events
