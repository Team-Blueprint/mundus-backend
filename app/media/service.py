import hashlib
from fastapi import UploadFile, status
import cloudinary
import cloudinary.uploader
from app.config import settings
from app.core.exceptions import MundusException


def configure_cloudinary():
    if settings.CLOUDINARY_CLOUD_NAME and settings.CLOUDINARY_API_KEY and settings.CLOUDINARY_API_SECRET:
        cloudinary.config(
            cloud_name=settings.CLOUDINARY_CLOUD_NAME,
            api_key=settings.CLOUDINARY_API_KEY,
            api_secret=settings.CLOUDINARY_API_SECRET,
            secure=True,
        )


def compute_photo_sha256(content: bytes) -> str:
    """Compute SHA-256 hash of raw image content for duplicate reuse detection."""
    return hashlib.sha256(content).hexdigest()


async def upload_photo_service(file: UploadFile) -> dict:
    if not file.content_type or not file.content_type.startswith("image/"):
        raise MundusException(
            message="Only image files (e.g., JPEG, PNG) are allowed.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    content = await file.read()
    if not content:
        raise MundusException(
            message="Uploaded file is empty.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    photo_hash = compute_photo_sha256(content)

    configure_cloudinary()

    if settings.CLOUDINARY_CLOUD_NAME and settings.CLOUDINARY_API_KEY:
        try:
            upload_result = cloudinary.uploader.upload(
                content,
                folder="mundus_checkins",
                resource_type="image",
            )
            photo_url = upload_result.get("secure_url") or upload_result.get("url")
        except Exception as e:
            raise MundusException(
                message=f"Cloudinary upload failed: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
    else:
        # Development / fallback mock URL when Cloudinary keys are not yet set
        photo_url = f"https://res.cloudinary.com/mundus-demo/image/upload/v1/checkins/{photo_hash[:16]}.jpg"

    return {
        "photo_url": photo_url,
        "photo_hash": photo_hash,
        "filename": file.filename,
        "content_type": file.content_type,
        "size_bytes": len(content),
    }

