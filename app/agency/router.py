from fastapi import APIRouter, Depends, status, BackgroundTasks
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth.deps import require_role
from app.auth.models import User, UserRole
from app.agency.schemas import (
    AgencyAccessRequestCreate,
    AgencyAccessRequestResponse,
    StaffInviteRequest,
    StaffResponse,
)
import app.agency.service as agency_service

router = APIRouter(prefix="/agency", tags=["Agency"])


@router.post("/request-access", response_model=AgencyAccessRequestResponse, status_code=status.HTTP_201_CREATED)
def request_agency_access(
    data: AgencyAccessRequestCreate,
    db: Session = Depends(get_db),
):
    """Public endpoint for state agency personnel to request dashboard administrative access."""
    return agency_service.create_access_request_service(db, data)


@router.get("/requests", response_model=list[AgencyAccessRequestResponse], status_code=status.HTTP_200_OK)
def list_agency_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.AGENCY])),
):
    """List pending and reviewed agency access requests (Agency admin view)."""
    return agency_service.list_access_requests_service(db)


# ---------------------------------------------------------------------------
# Staff management endpoints
# ---------------------------------------------------------------------------

@router.get("/staff", response_model=list[StaffResponse], status_code=status.HTTP_200_OK)
def list_staff(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.AGENCY])),
):
    """List all agency staff accounts."""
    return agency_service.list_staff_service(db)


@router.post("/staff/invite", response_model=StaffResponse, status_code=status.HTTP_201_CREATED)
async def invite_staff(
    data: StaffInviteRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.AGENCY])),
):
    """
    Create a new agency staff account and email login credentials.
    Temp password is sent by email only — never returned in the response.
    """
    return await agency_service.invite_staff_service(db, data, current_user, background_tasks=background_tasks)


@router.patch("/staff/{staff_id}/deactivate", status_code=status.HTTP_200_OK)
def deactivate_staff(
    staff_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.AGENCY])),
):
    """Deactivate an agency staff member (prevents login, preserves audit history)."""
    return agency_service.deactivate_staff_service(db, staff_id)


@router.patch("/staff/{staff_id}/reactivate", status_code=status.HTTP_200_OK)
def reactivate_staff(
    staff_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.AGENCY])),
):
    """Reactivate a previously deactivated agency staff member."""
    return agency_service.reactivate_staff_service(db, staff_id)
