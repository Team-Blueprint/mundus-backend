from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth.deps import get_current_user, require_role
from app.auth.models import User, UserRole
from app.dump_points.schemas import DumpPointCreate, DumpPointUpdate, DumpPointAssign, DumpPointResponse
import app.dump_points.service as dump_point_service

router = APIRouter(prefix="/dump-points", tags=["Dump Points"])


@router.post("", response_model=DumpPointResponse, status_code=status.HTTP_201_CREATED)
def create_dump_point(
    dump_point_in: DumpPointCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.AGENCY])),
):
    """Create a new dump point (Agency viewer / admin)."""
    return dump_point_service.create_dump_point(db, dump_point_in)


@router.get("", response_model=list[DumpPointResponse], status_code=status.HTTP_200_OK)
def list_dump_points(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List dump points. Supervisors only see their assigned sites; agency users see all."""
    return dump_point_service.list_dump_points(db, current_user)


@router.get("/{id}", response_model=DumpPointResponse, status_code=status.HTTP_200_OK)
def get_dump_point(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get dump point details by ID."""
    return dump_point_service.get_dump_point_by_id(db, id, current_user)


@router.get("/{id}/history", status_code=status.HTTP_200_OK)
def get_site_history_timeline(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get chronological timeline history of all check-ins, clearance events, and reporter flags for a site."""
    return dump_point_service.get_site_history_timeline(db, id, current_user)


@router.put("/{id}/assign", response_model=DumpPointResponse, status_code=status.HTTP_200_OK)
def assign_supervisor(
    id: int,
    assign_data: DumpPointAssign,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.AGENCY])),
):
    """Assign a contractor / supervisor to a dump point (Agency viewer / admin)."""
    return dump_point_service.assign_supervisor(db, id, assign_data)


@router.put("/{id}", response_model=DumpPointResponse, status_code=status.HTTP_200_OK)
def update_dump_point(
    id: int,
    update_data: DumpPointUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.AGENCY])),
):
    """Update dump point details."""
    return dump_point_service.update_dump_point(db, id, update_data)
