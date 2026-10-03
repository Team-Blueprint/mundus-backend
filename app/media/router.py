from fastapi import APIRouter, File, UploadFile, Form, status, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth.deps import get_current_user
from app.auth.models import User
from app.media.schemas import MediaUploadResponse
import app.media.service as media_service

router = APIRouter(prefix="/media", tags=["Media"])


@router.post("/upload", response_model=MediaUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_photo(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Upload a check-in photo to Cloudinary and return photo URL + SHA256 hash. Requires JWT."""
    return await media_service.upload_photo_service(file)


@router.post("/reporter-upload", response_model=MediaUploadResponse, status_code=status.HTTP_201_CREATED)
async def reporter_upload_photo(
    file: UploadFile = File(...),
    reporter_token: str = Form(..., description="Approved reporter token — no JWT required"),
    db: Session = Depends(get_db),
):
    """
    Public upload endpoint for community reporters (no JWT).
    Validates reporter_token belongs to an APPROVED reporter.
    Returns { photo_url, photo_hash } for use in POST /reporters/flag-site.
    """
    from app.reporters.models import Reporter, ReporterStatus

    reporter = db.query(Reporter).filter(Reporter.token == reporter_token).first()
    if not reporter or reporter.status != ReporterStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired reporter token.",
        )

    return await media_service.upload_photo_service(file, folder="mundus_reporter_flags")
