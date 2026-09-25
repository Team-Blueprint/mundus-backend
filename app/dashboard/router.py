from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth.deps import require_role
from app.auth.models import User, UserRole
import app.dashboard.service as dashboard_service
from app.dashboard.schemas import DashboardStatsResponse, DashboardSummaryResponse


router = APIRouter(prefix="/dashboard", tags=["Agency Dashboard"])


@router.get("/stats", response_model=DashboardStatsResponse, status_code=status.HTTP_200_OK)
def get_dashboard_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.AGENCY])),
):
    """Retrieve summary statistics for the dashboard (total sites, on schedule, overdue, critical, flagged)."""
    return dashboard_service.get_dashboard_stats(db)


@router.get("/sites", response_model=DashboardSummaryResponse, status_code=status.HTTP_200_OK)
def get_dashboard_sites(
    status_filter: str | None = Query(None, alias="status", description="Filter by status: critical, overdue, on_schedule, flagged, all"),
    search: str | None = Query(None, description="Search by site name, contractor, or supervisor"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.AGENCY])),
):
    """Retrieve all dump point sites sorted by days since clearance (descending) with overdue red flags (Agency view only)."""
    return dashboard_service.get_agency_dashboard(db, status_filter=status_filter, search_query=search)
