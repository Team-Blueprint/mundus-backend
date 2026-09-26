from pydantic import BaseModel


class MediaUploadResponse(BaseModel):
    photo_url: str
    photo_hash: str
    filename: str | None = None
    content_type: str | None = None
    size_bytes: int | None = None
