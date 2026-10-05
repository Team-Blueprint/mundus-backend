import re
from datetime import datetime
from pydantic import BaseModel, Field, field_validator, ConfigDict
from app.dump_points.schemas import DumpPointResponse


class ReporterNominateRequest(BaseModel):
    site_id: str
    contractor_id: str | None = None
    name: str = Field(..., min_length=2, max_length=255)
    phone: str = Field(..., min_length=11, max_length=11)

    @field_validator("phone")
    @classmethod
    def validate_nigerian_phone(cls, v: str) -> str:
        clean = re.sub(r"\D", "", v)
        if len(clean) != 11 or not clean.startswith(("07", "08", "09")):
            raise ValueError("Phone number must be an 11-digit Nigerian number (e.g. 08031234567).")
        return clean


class ReporterRejectRequest(BaseModel):
    reason: str | None = None


class ReporterResponse(BaseModel):
    id: int
    name: str
    phone: str
    site_id: str
    site_name: str | None = None
    contractor_id: str | None = None
    status: str
    token: str | None = None
    rejection_reason: str | None = None
    created_at: datetime
    updated_at: datetime
    whatsapp_link: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ReporterApproveResponse(BaseModel):
    reporter: ReporterResponse
    token: str
    whatsapp_link: str


class PublicReporterSiteResponse(BaseModel):
    reporter: dict
    site: DumpPointResponse


class ReporterFlagCreate(BaseModel):
    site_id: str
    reporter_token: str | None = None
    note: str | None = None
    photo_url: str | None = Field(default=None, description="Evidence photo URL from /media/reporter-upload")


class ReporterFlagResponse(BaseModel):
    id: int
    site_id: str
    reporter_id: int | None = None
    reporter_name: str | None = None
    timestamp: datetime
    note: str | None = None
    photo_url: str | None = None

    model_config = ConfigDict(from_attributes=True)
