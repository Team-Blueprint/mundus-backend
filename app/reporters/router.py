from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth.deps import get_current_user, require_role
from app.auth.models import User, UserRole
from app.reporters.schemas import ReporterFlagCreate, ReporterFlagResponse
import app.reporters.service as reporter_service

router = APIRouter(prefix="/reporters", tags=["Reporters"])


@router.post("/flag-site", response_model=ReporterFlagResponse, status_code=status.HTTP_201_CREATED)
def flag_site_full(
    flag_in: ReporterFlagCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.REPORTER, UserRole.AGENCY])),
):
    """Flag a site as full (Single-tap reporter flow with 12h rate limiting)."""
    return reporter_service.flag_site_full_service(db, flag_in, current_user)


@router.get("/site/{site_id}/flags", response_model=list[ReporterFlagResponse], status_code=status.HTTP_200_OK)
def list_site_flags(
    site_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all reporter flags for a dump point."""
    return reporter_service.list_site_flags_service(db, site_id)

