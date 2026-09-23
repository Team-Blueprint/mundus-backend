from sqlalchemy.orm import Session
from app.dump_points.models import DumpPoint
from app.dashboard.schemas import DashboardSiteResponse, DashboardSummaryResponse


def get_agency_dashboard(db: Session) -> DashboardSummaryResponse:
    sites = db.query(DumpPoint).all()
    dashboard_sites = [DashboardSiteResponse.from_dump_point(s) for s in sites]

    # Sort descending by days_since_last_clearance
    # Sites never cleared (days_since_last_clearance is None) are treated as infinity float('inf') to appear first
    sorted_sites = sorted(
        dashboard_sites,
        key=lambda s: s.days_since_last_clearance if s.days_since_last_clearance is not None else float('inf'),
        reverse=True,
    )

    overdue_count = sum(1 for s in sorted_sites if s.is_overdue)
    cleared_count = len(sorted_sites) - overdue_count

    return DashboardSummaryResponse(
        total_sites=len(sorted_sites),
        overdue_sites_count=overdue_count,
        cleared_sites_count=cleared_count,
        sites=sorted_sites,
    )

