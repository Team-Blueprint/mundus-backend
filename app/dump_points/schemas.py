from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict, Field
from app.config import settings


class DumpPointBase(BaseModel):
    name: str
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    assigned_contractor_id: str | None = None
    assigned_supervisor_id: int | None = None
    interval_days: int = 7


class DumpPointCreate(DumpPointBase):
    pass


class DumpPointUpdate(BaseModel):
    name: str | None = None
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    assigned_contractor_id: str | None = None
    assigned_supervisor_id: int | None = None
    interval_days: int | None = None


class DumpPointAssign(BaseModel):
    assigned_supervisor_id: int
    assigned_contractor_id: str | None = None


class DumpPointResponse(DumpPointBase):
    id: int
    last_clearance_timestamp: datetime | None = None
    created_at: datetime
    days_since_last_clearance: float | None = None
    is_overdue: bool = False

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm_computed(cls, dump_point):
        resp = cls.model_validate(dump_point)
        if dump_point.last_clearance_timestamp:
            now = datetime.now(timezone.utc)
            last_ts = dump_point.last_clearance_timestamp
            if last_ts.tzinfo is None:
                last_ts = last_ts.replace(tzinfo=timezone.utc)
            diff_days = (now - last_ts).total_seconds() / 86400.0
            resp.days_since_last_clearance = round(diff_days, 1)
            resp.is_overdue = diff_days >= settings.OVERDUE_THRESHOLD_DAYS
        else:
            resp.days_since_last_clearance = None
            resp.is_overdue = True  # Never cleared site is overdue by default
        return resp

