from fastapi import APIRouter, File, UploadFile, status, Depends
from app.auth.deps import get_current_user
from app.auth.models import User
import app.media.service as media_service

router = APIRouter(prefix="/media", tags=["Media"])


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_photo(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Upload a check-in photo to Cloudinary and return photo URL + SHA256 hash."""
    return await media_service.upload_photo_service(file)

