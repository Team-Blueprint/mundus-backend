from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth.deps import get_current_user, require_role
from app.auth.models import User, UserRole
from app.dump_points.schemas import DumpPointCreate, DumpPointUpdate, DumpPointAssign, DumpPointResponse
import app.dump_points.service as dump_point_service

router = APIRouter(prefix="/dump-points", tags=["Dump Points"])


# --- Create & List ---

# @router.post("", response_model=DumpPointResponse, status_code=status.HTTP_201_CREATED)
@router.post("/create", response_model=DumpPointResponse, status_code=status.HTTP_201_CREATED)
def create_dump_point(
    dump_point_in: DumpPointCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.AGENCY])),
):
    """Create a new dump point (Agency viewer / admin)."""
    return dump_point_service.create_dump_point(db, dump_point_in)


# @router.get("", response_model=list[DumpPointResponse], status_code=status.HTTP_200_OK)
@router.get("/all", response_model=list[DumpPointResponse], status_code=status.HTTP_200_OK)
def list_dump_points(
    status_filter: str | None = Query(None, alias="status", description="Filter by status: critical, overdue, on_schedule, flagged, all"),
    search: str | None = Query(None, description="Search by site name, code, sector, contractor, or contractor"),
    limit: int = Query(10, ge=1, le=10000, description="Max items to return"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List dump points. Contractors only see their assigned sites; agency users see all."""
    return dump_point_service.list_dump_points(db, current_user, status_filter=status_filter, search_query=search, limit=limit, offset=offset)


# --- Static / Explicit Sub-paths (Placed before wildcard /{id}) ---

# @router.get("/history/{id}", status_code=status.HTTP_200_OK)
@router.get("/{id}/history", status_code=status.HTTP_200_OK)
def get_site_history_timeline(
    id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get chronological timeline history of all check-ins, clearance events, and reporter flags for a site."""
    return dump_point_service.get_site_history_timeline(db, id, current_user)


@router.get("/detail/{id}", response_model=DumpPointResponse, status_code=status.HTTP_200_OK)
def get_dump_point_detail(
    id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get dump point details by ID (Explicit route)."""
    return dump_point_service.get_dump_point_by_id(db, id, current_user)


# @router.put("/assign/{id}", response_model=DumpPointResponse, status_code=status.HTTP_200_OK)
@router.put("/{id}/assign", response_model=DumpPointResponse, status_code=status.HTTP_200_OK)
def assign_contractor(
    id: str,
    assign_data: DumpPointAssign,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.AGENCY])),
):
    """Assign a contractor to a dump point (Agency viewer / admin)."""
    return dump_point_service.assign_dump_point(db, id, assign_data)


@router.put("/update/{id}", response_model=DumpPointResponse, status_code=status.HTTP_200_OK)
def update_dump_point_explicit(
    id: str,
    update_data: DumpPointUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.AGENCY])),
):
    """Update dump point details (Explicit route)."""
    return dump_point_service.update_dump_point(db, id, update_data)


@router.delete("/delete/{id}", status_code=status.HTTP_200_OK)
# @router.delete("/{id}", status_code=status.HTTP_200_OK)
def delete_dump_point(
    id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.AGENCY])),
):
    """Remove a dump point from the municipal registry (Agency admin only)."""
    return dump_point_service.delete_dump_point(db, id)


# --- Wildcard ID Routes ---

@router.get("/{id}", response_model=DumpPointResponse, status_code=status.HTTP_200_OK)
def get_dump_point(
    id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get dump point details by ID."""
    return dump_point_service.get_dump_point_by_id(db, id, current_user)


@router.put("/{id}", response_model=DumpPointResponse, status_code=status.HTTP_200_OK)
def update_dump_point(
    id: str,
    update_data: DumpPointUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.AGENCY])),
):
    """Update dump point details."""
    return dump_point_service.update_dump_point(db, id, update_data)
