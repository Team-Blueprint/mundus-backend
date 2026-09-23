from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth.deps import get_current_user, require_role
from app.auth.models import User, UserRole
from app.check_ins.schemas import CheckInCreate, CheckInResponse
import app.check_ins.service as check_in_service

router = APIRouter(prefix="/check-ins", tags=["Check-Ins"])


@router.post("", response_model=CheckInResponse, status_code=status.HTTP_201_CREATED)
def submit_check_in(
    check_in_in: CheckInCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPERVISOR])),
):
    """Submit a before or after clearance check-in photo + GPS coordinates (Contractor Supervisor)."""
    return check_in_service.submit_check_in_service(db, check_in_in, current_user)


@router.get("", response_model=list[CheckInResponse], status_code=status.HTTP_200_OK)
def list_check_ins(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List check-in history."""
    return check_in_service.list_all_check_ins(db, current_user)


@router.get("/site/{site_id}", response_model=list[CheckInResponse], status_code=status.HTTP_200_OK)
def list_site_check_ins(
    site_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List check-ins for a specific dump point site."""
    return check_in_service.list_site_check_ins(db, site_id, current_user)

