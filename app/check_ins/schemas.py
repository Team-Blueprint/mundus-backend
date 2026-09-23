from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from app.check_ins.models import CheckInType, CheckInStatus


class CheckInCreate(BaseModel):
    site_id: int
    type: CheckInType
    photo_url: str
    photo_hash: str
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    device_timestamp: datetime


class CheckInResponse(BaseModel):
    id: int
    site_id: int
    supervisor_id: int
    type: CheckInType
    photo_url: str
    photo_hash: str
    latitude: float
    longitude: float
    distance_from_site_meters: float
    device_timestamp: datetime
    server_timestamp: datetime
    status: CheckInStatus
    flags: list[str] = []

    model_config = ConfigDict(from_attributes=True)

