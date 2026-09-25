from app.auth.models import User, UserRole
from app.dump_points.service import list_dump_points
from app.dashboard.schemas import DashboardStatsResponse, DashboardSummaryResponse
from sqlalchemy.orm import Session



def get_dashboard_stats(db: Session) -> DashboardStatsResponse:
    # Dummy agency user to get all dump points without supervisor scoping
    admin_context = User(id=0, role=UserRole.AGENCY)
    all_sites = list_dump_points(db, admin_context)

    total_sites = len(all_sites)
    on_schedule_count = sum(1 for s in all_sites if s.status == "on_schedule")
    overdue_count = sum(1 for s in all_sites if s.status == "overdue")
    critical_count = sum(1 for s in all_sites if s.status == "critical")
    flagged_count = sum(1 for s in all_sites if len(s.flags) > 0)

    return DashboardStatsResponse(
        total_sites=total_sites,
        on_schedule_count=on_schedule_count,
        overdue_count=overdue_count,
        critical_count=critical_count,
        flagged_count=flagged_count,
    )


def get_agency_dashboard(
    db: Session,
    status_filter: str | None = None,
    search_query: str | None = None,
) -> DashboardSummaryResponse:
    admin_context = User(id=0, role=UserRole.AGENCY)
    all_sites = list_dump_points(db, admin_context)

    total_sites = len(all_sites)
    on_schedule_count = sum(1 for s in all_sites if s.status == "on_schedule")
    overdue_count = sum(1 for s in all_sites if s.status == "overdue")
    critical_count = sum(1 for s in all_sites if s.status == "critical")
    flagged_count = sum(1 for s in all_sites if len(s.flags) > 0)

    # Apply filtering for the returned sites array
    filtered_sites = list_dump_points(
        db, admin_context, status_filter=status_filter, search_query=search_query
    )
    return DashboardSummaryResponse(
        total_sites=total_sites,
        on_schedule_count=on_schedule_count,
        overdue_count=overdue_count,
        critical_count=critical_count,
        flagged_count=flagged_count,
        sites=filtered_sites,
    )

