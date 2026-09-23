from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth.deps import require_role
from app.auth.models import User, UserRole
from app.dashboard.schemas import DashboardSummaryResponse
import app.dashboard.service as dashboard_service

router = APIRouter(prefix="/dashboard", tags=["Agency Dashboard"])


@router.get("/sites", response_model=DashboardSummaryResponse, status_code=status.HTTP_200_OK)
def get_dashboard_sites(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.AGENCY])),
):
    """Retrieve all dump point sites sorted by days since clearance (descending) with overdue red flags (Agency view only)."""
    return dashboard_service.get_agency_dashboard(db)

