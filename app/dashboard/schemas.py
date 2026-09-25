from pydantic import BaseModel
from app.dump_points.schemas import DumpPointResponse

# DashboardSiteResponse is identical to DumpPointResponse
DashboardSiteResponse = DumpPointResponse


class DashboardStatsResponse(BaseModel):
    total_sites: int
    total_contractors: int = 4
    on_schedule_count: int
    overdue_count: int
    critical_count: int
    flagged_count: int


class DashboardSummaryResponse(BaseModel):
    total_sites: int
    total_contractors: int = 4
    on_schedule_count: int
    overdue_count: int
    critical_count: int
    flagged_count: int
    sites: list[DumpPointResponse]


class ContractorDumpPointItem(BaseModel):
    id: int
    name: str
    status: str
    formatted_last_cleared: str | None = None
    days_since_last_clearance: float | None = None


class ContractorGroupResponse(BaseModel):
    contractor_id: str
    contractor_name: str
    total_sites: int
    on_schedule_sites: int
    overdue_sites: int
    critical_sites: int
    sites: list[ContractorDumpPointItem]


class ContractorDashboardResponse(BaseModel):
    total_contractors: int
    contractors: list[ContractorGroupResponse]
