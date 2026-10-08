from fastapi import APIRouter, Depends, status, Query, Response
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

router = APIRouter(tags=["Contractors"])


# --- Agency Contractor Directory ---

@router.get("/contractors", response_model=list[ContractorResponse], status_code=status.HTTP_200_OK)
@router.get("/contractors/all", response_model=list[ContractorResponse], status_code=status.HTTP_200_OK)
def list_contractors(
    response: Response,
    q: str | None = Query(None, description="Search by contractor name or contractor"),
    status_filter: str | None = Query(None, alias="status", description="Filter: critical, overdue, on_schedule, all"),
    needs_attention: bool = Query(False, description="True = only contractors with overdue or critical sites"),
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.AGENCY, UserRole.CONTRACTOR])),
):
    """List contractors with site counts and overdue indicators (Agency view & assignment dropdowns)."""
    items, total = contractor_service.list_contractors_service(
        db, q=q, status_filter=status_filter, needs_attention=needs_attention, limit=limit, offset=offset, current_user=current_user, return_total=True
    )
    response.headers["X-Total-Count"] = str(total)
    return items


@router.post("/contractors", response_model=ContractorResponse, status_code=status.HTTP_201_CREATED)
@router.post("/contractors/new", response_model=ContractorResponse, status_code=status.HTTP_201_CREATED)
def create_contractor(
    data: ContractorCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.AGENCY])),
):
    """Add a new waste management contractor and register its contractor account."""
    return contractor_service.create_contractor_service(db, data)


# --- Contractor Field App Endpoints ---

@router.get("/contractor/sites", response_model=list[DumpPointResponse], status_code=status.HTTP_200_OK)
def get_contractor_sites(
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.CONTRACTOR])),
):
    """Retrieve assigned dump points for the logged-in contractor, sorted most overdue first."""
    sites = contractor_service.get_contractor_sites_service(db, current_user)
    response.headers["X-Total-Count"] = str(len(sites))
    return sites


@router.get("/contractor/submissions", response_model=list[SubmissionPairResponse], status_code=status.HTTP_200_OK)
def get_contractor_submissions(
    response: Response,
    site_id: str | None = Query(None, description="Filter submissions by site ID"),
    status_filter: str | None = Query(None, alias="status", description="Filter: complete, pending, flagged, all"),
    q: str | None = Query(None, description="Search by site name substring"),
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.CONTRACTOR])),
):
    """Contractor check-in history grouped by site and calendar day into before/after clearance pairs."""
    items, total = contractor_service.get_contractor_submissions_service(
        db, current_user, site_id=site_id, status_filter=status_filter, q=q, limit=limit, offset=offset, return_total=True
    )
    response.headers["X-Total-Count"] = str(total)
    return items


@router.get("/contractor/alerts", response_model=list[ContractorAlertResponse], status_code=status.HTTP_200_OK)
def get_contractor_alerts(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.CONTRACTOR, UserRole.AGENCY])),
):
    """Retrieve active site full alerts for contractor assigned dump points."""
    return contractor_service.get_contractor_alerts_service(db, current_user)


@router.post("/contractor/alerts/{site_id}/seen", status_code=status.HTTP_200_OK)
def mark_alert_seen(
    site_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.CONTRACTOR, UserRole.AGENCY])),
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
    """Change user password (Contractor settings screen)."""
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
