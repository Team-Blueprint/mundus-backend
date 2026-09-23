from sqlalchemy.orm import Session
from app.dump_points.models import DumpPoint
from app.dump_points.schemas import DumpPointCreate, DumpPointUpdate, DumpPointAssign, DumpPointResponse
from app.auth.models import User, UserRole
from app.core.exceptions import EntityNotFoundException, PermissionDeniedException


def create_dump_point(db: Session, dump_point_in: DumpPointCreate) -> DumpPointResponse:
    db_obj = DumpPoint(
        name=dump_point_in.name,
        latitude=dump_point_in.latitude,
        longitude=dump_point_in.longitude,
        assigned_contractor_id=dump_point_in.assigned_contractor_id,
        assigned_supervisor_id=dump_point_in.assigned_supervisor_id,
        interval_days=dump_point_in.interval_days,
    )
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return DumpPointResponse.from_orm_computed(db_obj)


def list_dump_points(db: Session, current_user: User) -> list[DumpPointResponse]:
    query = db.query(DumpPoint)
    if current_user.role == UserRole.SUPERVISOR:
        query = query.filter(DumpPoint.assigned_supervisor_id == current_user.id)

    dump_points = query.all()
    return [DumpPointResponse.from_orm_computed(dp) for dp in dump_points]


def get_dump_point_by_id(db: Session, dump_point_id: int, current_user: User = None) -> DumpPointResponse:
    db_obj = db.query(DumpPoint).filter(DumpPoint.id == dump_point_id).first()
    if not db_obj:
        raise EntityNotFoundException("DumpPoint", dump_point_id)

    if current_user and current_user.role == UserRole.SUPERVISOR:
        if db_obj.assigned_supervisor_id != current_user.id:
            raise PermissionDeniedException("Supervisors can only access their assigned dump points.")

    return DumpPointResponse.from_orm_computed(db_obj)


def assign_supervisor(db: Session, dump_point_id: int, assign_data: DumpPointAssign) -> DumpPointResponse:
    db_obj = db.query(DumpPoint).filter(DumpPoint.id == dump_point_id).first()
    if not db_obj:
        raise EntityNotFoundException("DumpPoint", dump_point_id)

    db_obj.assigned_supervisor_id = assign_data.assigned_supervisor_id
    if assign_data.assigned_contractor_id:
        db_obj.assigned_contractor_id = assign_data.assigned_contractor_id

    db.commit()
    db.refresh(db_obj)
    return DumpPointResponse.from_orm_computed(db_obj)


def update_dump_point(db: Session, dump_point_id: int, update_data: DumpPointUpdate) -> DumpPointResponse:
    db_obj = db.query(DumpPoint).filter(DumpPoint.id == dump_point_id).first()
    if not db_obj:
        raise EntityNotFoundException("DumpPoint", dump_point_id)

    for field, value in update_data.model_dump(exclude_unset=True).items():
        setattr(db_obj, field, value)

    db.commit()
    db.refresh(db_obj)
    return DumpPointResponse.from_orm_computed(db_obj)


def get_site_history_timeline(db: Session, dump_point_id: int, current_user: User) -> dict:
    dump_point = get_dump_point_by_id(db, dump_point_id, current_user)

    from app.check_ins.models import CheckIn
    from app.check_ins.schemas import CheckInResponse
    from app.reporters.models import ReporterFlag
    from app.reporters.schemas import ReporterFlagResponse

    check_ins = db.query(CheckIn).filter(CheckIn.site_id == dump_point_id).order_by(CheckIn.server_timestamp.desc()).all()
    reporter_flags = db.query(ReporterFlag).filter(ReporterFlag.site_id == dump_point_id).order_by(ReporterFlag.timestamp.desc()).all()

    events = []
    for ci in check_ins:
        events.append({
            "event_type": f"check_in_{ci.type.value}",
            "timestamp": ci.server_timestamp.isoformat(),
            "details": CheckInResponse.model_validate(ci).model_dump(),
        })

    for rf in reporter_flags:
        events.append({
            "event_type": "reporter_flag_site_full",
            "timestamp": rf.timestamp.isoformat(),
            "details": ReporterFlagResponse.from_orm_custom(rf).model_dump(),
        })

    events.sort(key=lambda e: e["timestamp"], reverse=True)

    return {
        "site": dump_point.model_dump(),
        "total_events": len(events),
        "timeline": events,
    }
