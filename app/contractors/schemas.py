from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from app.dump_points.schemas import DumpPointResponse
from app.check_ins.schemas import CheckInResponse


class ContractorCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(..., min_length=6)


class ContractorResponse(BaseModel):
    id: str
    name: str
    email: str
    site_count: int = 0
    overdue: int = 0
    critical: int = 0
    on_schedule: int = 0
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class PasswordChangeRequest(BaseModel):
    current: str | None = None
    current_password: str | None = None
    new: str | None = None
    new_password: str | None = None


class ContractorAlertResponse(BaseModel):
    id: int
    site_id: str
    site_name: str | None = None
    message: str
    is_seen: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SubmissionPairResponse(BaseModel):
    date: str
    site_id: str
    site_name: str
    before: CheckInResponse | None = None
    after: CheckInResponse | None = None
    status: str = "complete"  # complete, in_progress, partial
