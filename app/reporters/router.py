from fastapi import APIRouter, Depends, status, Query, BackgroundTasks
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth.deps import get_current_user, get_current_user_optional, require_role
from app.auth.models import User, UserRole
from app.reporters.schemas import (
    ReporterNominateRequest,
    ReporterResponse,
    ReporterApproveResponse,
    ReporterRejectRequest,
    PublicReporterSiteResponse,
    ReporterFlagCreate,
    ReporterFlagResponse,
)
import app.reporters.service as reporter_service

router = APIRouter(tags=["Community Reporters"])


@router.post("/reporters/nominate", response_model=ReporterResponse, status_code=status.HTTP_201_CREATED)
def nominate_reporter(
    payload: ReporterNominateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPERVISOR, UserRole.AGENCY])),
):
    """Nominate a community reporter for a dump point site (Contractor supervisor or Agency)."""
    return reporter_service.nominate_reporter_service(db, payload)


@router.get("/reporters", response_model=list[ReporterResponse], status_code=status.HTTP_200_OK)
def list_reporters(
    site_id: int | None = Query(None, description="Filter reporters by site ID"),
    status_filter: str | None = Query(None, alias="status", description="Filter by status: pending, approved, rejected, revoked, all"),
    q: str | None = Query(None, description="Search by reporter name or phone"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List reporter roster (Agency sees tokens & WhatsApp share links; Supervisors see masked tokens)."""
    return reporter_service.list_reporters_service(
        db, current_user, site_id=site_id, status_filter=status_filter, q=q
    )


@router.post("/reporters/{id}/approve", response_model=ReporterApproveResponse, status_code=status.HTTP_200_OK)
def approve_reporter(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.AGENCY])),
):
    """Approve a nominated reporter, activate reporting token, and generate WhatsApp deep link."""
    return reporter_service.approve_reporter_service(db, id)


@router.post("/reporters/{id}/reject", response_model=ReporterResponse, status_code=status.HTTP_200_OK)
def reject_reporter(
    id: int,
    payload: ReporterRejectRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.AGENCY])),
):
    """Reject a nominated reporter with an optional rejection reason."""
    reason = payload.reason if payload else None
    return reporter_service.reject_reporter_service(db, id, reason)


@router.post("/reporters/{id}/revoke", response_model=ReporterResponse, status_code=status.HTTP_200_OK)
def revoke_reporter(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.AGENCY])),
):
    """Revoke an approved reporter and invalidate their reporting link."""
    return reporter_service.revoke_reporter_service(db, id)


# --- Public Community Reporting Endpoints ---

@router.get("/r/{token}", response_model=PublicReporterSiteResponse, status_code=status.HTTP_200_OK)
def resolve_reporter_token(
    token: str,
    db: Session = Depends(get_db),
):
    """Public endpoint to resolve community reporter token and retrieve dump point site details."""
    return reporter_service.resolve_public_reporter_token(db, token)


@router.post("/reporters/flag-site", response_model=ReporterFlagResponse, status_code=status.HTTP_201_CREATED)
def flag_site_full(
    flag_in: ReporterFlagCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    """Public single-tap flag endpoint via reporter token (or authenticated JWT) with 12h site lock."""
    return reporter_service.flag_site_full_service(
        db, flag_in, current_user=current_user, background_tasks=background_tasks
    )


@router.get("/reporters/site/{site_id}/flags", response_model=list[ReporterFlagResponse], status_code=status.HTTP_200_OK)
def list_site_flags(
    site_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all reporter flags for a dump point."""
    return reporter_service.list_site_flags_service(db, site_id)
