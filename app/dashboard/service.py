from app.auth.models import User, UserRole
from app.dump_points.service import list_dump_points
from app.dashboard.schemas import (
    DashboardStatsResponse,
    DashboardSummaryResponse,
    ContractorDashboardResponse,
    ContractorGroupResponse,
    ContractorDumpPointItem,
)
from sqlalchemy.orm import Session

CONTRACTOR_MAP = {
    "CTR-AK-001": "CleanCity Services",
    "CTR-AK-002": "EcoWaste Management",
    "CTR-AK-003": "GreenGlobe Logistics",
    "CTR-AK-004": "Apex Sanitation",
}


def get_dashboard_stats(db: Session) -> DashboardStatsResponse:
    # Dummy agency user to get all dump points without contractor scoping
    admin_context = User(id=0, role=UserRole.AGENCY)
    all_sites = list_dump_points(db, admin_context)

    total_sites = len(all_sites)
    on_schedule_count = sum(1 for s in all_sites if s.status == "on_schedule")
    overdue_count = sum(1 for s in all_sites if s.status == "overdue")
    critical_count = sum(1 for s in all_sites if s.status == "critical")
    flagged_count = sum(1 for s in all_sites if len(s.flags) > 0)

    # Compute unique active contractors
    contractor_ids = {s.assigned_contractor_id for s in all_sites if s.assigned_contractor_id}
    total_contractors = max(len(contractor_ids), len(CONTRACTOR_MAP))

    return DashboardStatsResponse(
        total_sites=total_sites,
        total_contractors=total_contractors,
        on_schedule_count=on_schedule_count,
        cleared_sites_count=on_schedule_count,
        overdue_count=overdue_count,
        overdue_sites_count=overdue_count + critical_count,
        critical_count=critical_count,
        flagged_count=flagged_count,
    )


def get_agency_dashboard(
    db: Session,
    status_filter: str | None = None,
    search_query: str | None = None,
    contractor_filter: str | None = None,
    overdue_only: bool = False,
    limit: int = 10,
    offset: int = 0,
) -> DashboardSummaryResponse:
    admin_context = User(id=0, role=UserRole.AGENCY)
    all_sites = list_dump_points(db, admin_context, limit=10000)  # unfiltered for stats

    total_sites = len(all_sites)
    on_schedule_count = sum(1 for s in all_sites if s.status == "on_schedule")
    overdue_count = sum(1 for s in all_sites if s.status == "overdue")
    critical_count = sum(1 for s in all_sites if s.status == "critical")
    flagged_count = sum(1 for s in all_sites if len(s.flags) > 0)

    contractor_ids = {s.assigned_contractor_id for s in all_sites if s.assigned_contractor_id}
    total_contractors = max(len(contractor_ids), len(CONTRACTOR_MAP))

    # Resolve effective status_filter for overdue_only
    effective_status = status_filter
    if overdue_only and not effective_status:
        effective_status = "overdue"  # treated as overdue+critical in list_dump_points

    filtered_sites = list_dump_points(
        db, admin_context,
        status_filter=effective_status,
        search_query=search_query,
        limit=limit,
        offset=offset,
    )

    # Apply contractor name/id substring filter post-pagination if specified
    if contractor_filter:
        cf = contractor_filter.lower()
        filtered_sites = [
            s for s in filtered_sites
            if (s.assigned_contractor_name and cf in s.assigned_contractor_name.lower())
            or (s.assigned_contractor_id and cf in s.assigned_contractor_id.lower())
        ]

    return DashboardSummaryResponse(
        total_sites=total_sites,
        total_contractors=total_contractors,
        on_schedule_count=on_schedule_count,
        cleared_sites_count=on_schedule_count,
        overdue_count=overdue_count,
        overdue_sites_count=overdue_count + critical_count,
        critical_count=critical_count,
        flagged_count=flagged_count,
        sites=filtered_sites,
    )


def get_contractors_dashboard(
    db: Session,
    search_query: str | None = None,
) -> ContractorDashboardResponse:
    admin_context = User(id=0, role=UserRole.AGENCY)
    all_sites = list_dump_points(db, admin_context, search_query=search_query)

    # Group dump points by contractor ID
    grouped: dict[str, list] = {cid: [] for cid in CONTRACTOR_MAP.keys()}
    for s in all_sites:
        cid = s.assigned_contractor_id or "UNASSIGNED"
        if cid not in grouped:
            grouped[cid] = []
        grouped[cid].append(s)

    contractor_groups = []
    for cid, sites in grouped.items():
        cname = CONTRACTOR_MAP.get(cid, "Unassigned Contractor" if cid == "UNASSIGNED" else cid)
        on_sched = sum(1 for s in sites if s.status == "on_schedule")
        overdue = sum(1 for s in sites if s.status == "overdue")
        critical = sum(1 for s in sites if s.status == "critical")

        site_items = [
            ContractorDumpPointItem(
                id=s.id,
                name=s.name,
                status=s.status,
                formatted_last_cleared=s.formatted_last_cleared,
                days_since_last_clearance=s.days_since_last_clearance,
            )
            for s in sites
        ]

        contractor_groups.append(
            ContractorGroupResponse(
                contractor_id=cid,
                contractor_name=cname,
                total_sites=len(sites),
                on_schedule_sites=on_sched,
                overdue_sites=overdue,
                critical_sites=critical,
                sites=site_items,
            )
        )

    return ContractorDashboardResponse(
        total_contractors=len(contractor_groups),
        contractors=contractor_groups,
    )
