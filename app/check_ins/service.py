import math
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from fastapi import status
from app.check_ins.models import CheckIn, CheckInType, CheckInStatus
from app.check_ins.schemas import CheckInCreate, CheckInResponse
from app.dump_points.models import DumpPoint
from app.auth.models import User, UserRole
from app.config import settings
from app.core.exceptions import MundusException, EntityNotFoundException, PermissionDeniedException


def calculate_haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in meters between two coordinates using the Haversine formula."""
    R = 6371000.0  # Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


def submit_check_in_service(db: Session, check_in_in: CheckInCreate, current_user: User) -> CheckInResponse:
    # 1. Retrieve target dump point
    site = db.query(DumpPoint).filter(DumpPoint.id == check_in_in.site_id).first()
    if not site:
        raise EntityNotFoundException("DumpPoint", check_in_in.site_id)

    # 2. Supervisor scoping check
    if current_user.role == UserRole.SUPERVISOR and site.assigned_supervisor_id != current_user.id:
        raise PermissionDeniedException("Supervisors can only submit check-ins for their assigned dump points.")

    # 3. Calculate Haversine geofence distance
    distance_meters = calculate_haversine_distance(
        check_in_in.latitude, check_in_in.longitude,
        site.latitude, site.longitude
    )

    flags = []
    status_result = CheckInStatus.VALID

    # Geofence check
    if distance_meters > settings.GEOFENCE_RADIUS_METERS:
        flags.append(f"location_mismatch: Submitted position is {distance_meters:.1f}m away from dump point (allowed: {settings.GEOFENCE_RADIUS_METERS:.1f}m)")
        status_result = CheckInStatus.LOCATION_MISMATCH

    # 4. Photo hash duplicate detection
    existing_photo_hash = db.query(CheckIn).filter(CheckIn.photo_hash == check_in_in.photo_hash).first()
    if existing_photo_hash:
        flags.append(f"duplicate_photo_reused: Photo hash matches prior check-in #{existing_photo_hash.id}")
        if status_result == CheckInStatus.VALID:
            status_result = CheckInStatus.FLAGGED

    # 5. Timestamp sanity check (flag if device vs server > 15 mins)
    server_now = datetime.now(timezone.utc)
    device_ts = check_in_in.device_timestamp
    if device_ts.tzinfo is None:
        device_ts = device_ts.replace(tzinfo=timezone.utc)

    time_diff_minutes = abs((server_now - device_ts).total_seconds()) / 60.0
    if time_diff_minutes > 15.0:
        flags.append(f"timestamp_skew: Device timestamp differs from server receipt by {time_diff_minutes:.1f} minutes")
        if status_result == CheckInStatus.VALID:
            status_result = CheckInStatus.FLAGGED

    # Save check-in record
    check_in_db = CheckIn(
        site_id=check_in_in.site_id,
        supervisor_id=current_user.id,
        type=check_in_in.type,
        photo_url=check_in_in.photo_url,
        photo_hash=check_in_in.photo_hash,
        latitude=check_in_in.latitude,
        longitude=check_in_in.longitude,
        distance_from_site_meters=round(distance_meters, 2),
        device_timestamp=device_ts,
        server_timestamp=server_now,
        status=status_result,
        flags=flags,
    )

    db.add(check_in_db)

    # 6. Update dump point last_clearance_timestamp if this is an AFTER check-in
    if check_in_in.type == CheckInType.AFTER:
        site.last_clearance_timestamp = server_now

    db.commit()
    db.refresh(check_in_db)

    return CheckInResponse.model_validate(check_in_db)


def list_site_check_ins(db: Session, site_id: int, current_user: User) -> list[CheckInResponse]:
    site = db.query(DumpPoint).filter(DumpPoint.id == site_id).first()
    if not site:
        raise EntityNotFoundException("DumpPoint", site_id)

    if current_user.role == UserRole.SUPERVISOR and site.assigned_supervisor_id != current_user.id:
        raise PermissionDeniedException("Supervisors can only view check-ins for their assigned sites.")

    check_ins = db.query(CheckIn).filter(CheckIn.site_id == site_id).order_by(CheckIn.server_timestamp.desc()).all()
    return [CheckInResponse.model_validate(ci) for ci in check_ins]


def list_all_check_ins(db: Session, current_user: User) -> list[CheckInResponse]:
    query = db.query(CheckIn)
    if current_user.role == UserRole.SUPERVISOR:
        query = query.filter(CheckIn.supervisor_id == current_user.id)

    check_ins = query.order_by(CheckIn.server_timestamp.desc()).all()
    return [CheckInResponse.model_validate(ci) for ci in check_ins]

