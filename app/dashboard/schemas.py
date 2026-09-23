from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict
from app.config import settings


class DashboardSiteResponse(BaseModel):
    id: int
    name: str
    latitude: float
    longitude: float
    assigned_contractor_id: str | None = None
    assigned_supervisor_id: int | None = None
    assigned_supervisor_name: str | None = None
    interval_days: int
    last_clearance_timestamp: datetime | None = None
    days_since_last_clearance: float | None = None
    is_overdue: bool = False

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_dump_point(cls, site):
        sup_name = site.assigned_supervisor.full_name if site.assigned_supervisor else None
        
        days_since = None
        is_overdue = True  # Never cleared is overdue

        if site.last_clearance_timestamp:
            now = datetime.now(timezone.utc)
            last_ts = site.last_clearance_timestamp
            if last_ts.tzinfo is None:
                last_ts = last_ts.replace(tzinfo=timezone.utc)
            
            diff_days = (now - last_ts).total_seconds() / 86400.0
            days_since = round(diff_days, 1)
            is_overdue = diff_days >= settings.OVERDUE_THRESHOLD_DAYS

        return cls(
            id=site.id,
            name=site.name,
            latitude=site.latitude,
            longitude=site.longitude,
            assigned_contractor_id=site.assigned_contractor_id,
            assigned_supervisor_id=site.assigned_supervisor_id,
            assigned_supervisor_name=sup_name,
            interval_days=site.interval_days,
            last_clearance_timestamp=site.last_clearance_timestamp,
            days_since_last_clearance=days_since,
            is_overdue=is_overdue,
        )


class DashboardSummaryResponse(BaseModel):
    total_sites: int
    overdue_sites_count: int
    cleared_sites_count: int
    sites: list[DashboardSiteResponse]

