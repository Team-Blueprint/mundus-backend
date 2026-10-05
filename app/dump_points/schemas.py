from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, ConfigDict, Field
from app.config import settings


class DumpPointBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    code: str | None = None
    sector: str | None = None
    assigned_contractor_id: str | None = None
    interval_days: int = Field(default=7, ge=1)


class DumpPointCreate(DumpPointBase):
    pass


class DumpPointUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=255)
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    code: str | None = None
    sector: str | None = None
    assigned_contractor_id: str | None = None
    interval_days: int | None = Field(None, ge=1)


class DumpPointAssign(BaseModel):
    assigned_contractor_id: str | None = None


class DumpPointResponse(DumpPointBase):
    id: str
    assigned_contractor_name: str | None = None
    assigned_contractor_email: str | None = None
    last_clearance_timestamp: datetime | None = None
    created_at: datetime
    formatted_last_cleared: str | None = None
    days_since_last_clearance: float | None = None
    is_overdue: bool = False
    status: str = "on_schedule"
    flags: list[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm_computed(cls, dump_point, flags: list[str] | None = None):
        resp = cls.model_validate(dump_point)

        if hasattr(dump_point, "assigned_contractor") and dump_point.assigned_contractor:
            resp.assigned_contractor_name = dump_point.assigned_contractor.name
            resp.assigned_contractor_email = dump_point.assigned_contractor.email
        else:
            resp.assigned_contractor_name = None
            resp.assigned_contractor_email = None

        if dump_point.last_clearance_timestamp:
            now = datetime.now(timezone.utc)
            last_ts = dump_point.last_clearance_timestamp

            if last_ts.tzinfo is None:
                last_ts = last_ts.replace(tzinfo=timezone.utc)
            diff_days = (now - last_ts).total_seconds() / 86400.0
            resp.days_since_last_clearance = round(diff_days, 1)
            resp.formatted_last_cleared = last_ts.strftime("%d %b %Y, %I:%M %p")

            if diff_days > settings.OVERDUE_THRESHOLD_DAYS:
                resp.status = "critical"
                resp.is_overdue = True
            elif diff_days >= dump_point.interval_days:
                resp.status = "overdue"
                resp.is_overdue = True
            else:
                resp.status = "on_schedule"
                resp.is_overdue = False
        else:
            resp.days_since_last_clearance = None
            resp.formatted_last_cleared = None
            resp.status = "critical"
            resp.is_overdue = True

        if flags is not None:
            resp.flags = flags

        return resp


class HistoryEventItem(BaseModel):
    kind: str  # check_in, flag, clearance
    at: str
    actor: str
    note: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
