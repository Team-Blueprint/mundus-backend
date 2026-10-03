from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth.deps import get_current_user, require_role
from app.auth.models import User, UserRole
from app.contractors.schemas import (
    ContractorCreate,
    ContractorResponse,
    ContractorAlertResponse,
    SubmissionPairResponse,
    PasswordChangeRequest,
)
from app.dump_points.schemas import DumpPointResponse
import app.contractors.service as contractor_service

router = APIRouter(tags=["Contractors & Supervisors"])


# --- Agency Contractor Directory ---

@router.get("/contractors/all", response_model=list[ContractorResponse], status_code=status.HTTP_200_OK)
def list_contractors(
    q: str | None = Query(None, description="Search by contractor name or supervisor"),
    status_filter: str | None = Query(None, alias="status", description="Filter: critical, overdue, on_schedule, all"),
    needs_attention: bool = Query(False, description="True = only contractors with overdue or critical sites"),
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.AGENCY])),
):
    """List contractors with site counts and overdue indicators (Agency view & assignment dropdowns)."""
    return contractor_service.list_contractors_service(
        db, q=q, status_filter=status_filter, needs_attention=needs_attention, limit=limit, offset=offset
    )


@router.post("/contractors/new", response_model=ContractorResponse, status_code=status.HTTP_201_CREATED)
def create_contractor(
    data: ContractorCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.AGENCY])),
):
    """Add a new waste management contractor and register its supervisor account."""
    return contractor_service.create_contractor_service(db, data)


# --- Supervisor Field App Endpoints ---

@router.get("/contractor/sites", response_model=list[DumpPointResponse], status_code=status.HTTP_200_OK)
def get_supervisor_sites(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPERVISOR])),
):
    """Retrieve assigned dump points for the logged-in supervisor, sorted most overdue first."""
    return contractor_service.get_supervisor_sites_service(db, current_user)


@router.get("/contractor/submissions", response_model=list[SubmissionPairResponse], status_code=status.HTTP_200_OK)
def get_supervisor_submissions(
    site_id: int | None = Query(None, description="Filter submissions by site ID"),
    status_filter: str | None = Query(None, alias="status", description="Filter: complete, pending, flagged, all"),
    q: str | None = Query(None, description="Search by site name substring"),
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPERVISOR])),
):
    """Supervisor check-in history grouped by site and calendar day into before/after clearance pairs."""
    return contractor_service.get_supervisor_submissions_service(
        db, current_user, site_id=site_id, status_filter=status_filter, q=q, limit=limit, offset=offset
    )


@router.get("/contractor/alerts", response_model=list[ContractorAlertResponse], status_code=status.HTTP_200_OK)
def get_contractor_alerts(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPERVISOR, UserRole.AGENCY])),
):
    """Retrieve active site full alerts for supervisor assigned dump points."""
    return contractor_service.get_contractor_alerts_service(db, current_user)


@router.post("/contractor/alerts/{site_id}/seen", status_code=status.HTTP_200_OK)
def mark_alert_seen(
    site_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPERVISOR, UserRole.AGENCY])),
):
    """Dismiss or mark 'reported full' banner alerts as seen for a site."""
    return contractor_service.mark_contractor_alert_seen_service(db, site_id, current_user)


# --- User Password Change ---

@router.patch("/users/{id}/password", status_code=status.HTTP_200_OK)
def change_user_password(
    id: int,
    payload: PasswordChangeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Change user password (Supervisor settings screen)."""
    new_pw = payload.new or payload.new_password
    curr_pw = payload.current or payload.current_password
    return contractor_service.change_user_password_service(
        db=db,
        user_id=id,
        current_user=current_user,
        current_password=curr_pw,
        new_password=new_pw,
    )


@router.patch("/users/password", status_code=status.HTTP_200_OK)
def change_my_password(
    payload: PasswordChangeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Change current authenticated user's password."""
    new_pw = payload.new or payload.new_password
    curr_pw = payload.current or payload.current_password
    return contractor_service.change_user_password_service(
        db=db,
        user_id=current_user.id,
        current_user=current_user,
        current_password=curr_pw,
        new_password=new_pw,
    )
