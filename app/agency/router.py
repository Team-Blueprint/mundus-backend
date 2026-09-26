from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth.deps import require_role
from app.auth.models import User, UserRole
from app.agency.schemas import AgencyAccessRequestCreate, AgencyAccessRequestResponse
import app.agency.service as agency_service

router = APIRouter(prefix="/agency", tags=["Agency Access Requests"])


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
