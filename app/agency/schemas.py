from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, ConfigDict


class AgencyAccessRequestCreate(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr


class AgencyAccessRequestResponse(BaseModel):
    id: int
    full_name: str
    email: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StaffInviteRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    make_admin: bool = False  # reserved for future role tiers; all staff get AGENCY role


class StaffResponse(BaseModel):
    id: int
    full_name: str | None
    email: str
    role: str
    is_active: bool
    is_agency_staff: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
