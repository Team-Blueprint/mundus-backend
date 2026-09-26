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
    assigned_supervisor_id: int | None = None
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
    assigned_supervisor_id: int | None = None
    interval_days: int | None = Field(None, ge=1)


class DumpPointAssign(BaseModel):
    assigned_supervisor_id: int | None = None
    assigned_contractor_id: str | None = None


class DumpPointResponse(DumpPointBase):
    id: int
    assigned_contractor_name: str | None = None
    assigned_supervisor_name: str | None = None
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

        if hasattr(dump_point, "assigned_supervisor") and dump_point.assigned_supervisor:
            resp.assigned_supervisor_name = (
                dump_point.assigned_supervisor.full_name or dump_point.assigned_supervisor.email
            )
        CONTRACTOR_NAME_MAP = {
            "CTR-AK-001": "CleanCity Services",
            "CTR-AK-002": "EcoWaste Management",
            "CTR-AK-003": "GreenGlobe Logistics",
            "CTR-AK-004": "Apex Sanitation",
        }
        if dump_point.assigned_contractor_id:
            resp.assigned_contractor_name = CONTRACTOR_NAME_MAP.get(
                dump_point.assigned_contractor_id, dump_point.assigned_contractor_id
            )
        else:
            resp.assigned_contractor_name = None

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
