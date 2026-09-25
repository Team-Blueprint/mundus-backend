from pydantic import BaseModel
from app.dump_points.schemas import DumpPointResponse

# DashboardSiteResponse is identical to DumpPointResponse
DashboardSiteResponse = DumpPointResponse


class DashboardStatsResponse(BaseModel):
    total_sites: int
    on_schedule_count: int
    overdue_count: int
    critical_count: int
    flagged_count: int


class DashboardSummaryResponse(BaseModel):
    on_schedule_count: int
    overdue_count: int
    critical_count: int
    flagged_count: int
    sites: list[DumpPointResponse]

