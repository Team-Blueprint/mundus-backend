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
