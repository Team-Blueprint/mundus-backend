import sys
import os
from datetime import datetime, timedelta, timezone

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import engine, Base, SessionLocal
from app.auth.models import User, UserRole
import app.check_ins.models  # noqa: Ensure CheckIn model is registered
import app.reporters.models  # noqa: Ensure ReporterFlag model is registered
from app.dump_points.models import DumpPoint
from app.core.security import get_password_hash


def seed():
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        demo_users = [
            {
                "email": "supervisor@mundus.org",
                "password": "Password123!",
                "full_name": "John Supervisor",
                "role": UserRole.SUPERVISOR,
            },
            {
                "email": "agency@mundus.org",
                "password": "Password123!",
                "full_name": "State Agency Viewer",
                "role": UserRole.AGENCY,
            },
            {
                "email": "reporter@mundus.org",
                "password": "Password123!",
                "full_name": "Site Reporter (Nwaniba)",
                "role": UserRole.REPORTER,
            },
        ]

        user_records = {}
        for udata in demo_users:
            existing = db.query(User).filter(User.email == udata["email"]).first()
            if not existing:
                user = User(
                    email=udata["email"],
                    hashed_password=get_password_hash(udata["password"]),
                    full_name=udata["full_name"],
                    role=udata["role"],
                    is_active=True,
                )
                db.add(user)
                db.commit()
                db.refresh(user)
                user_records[udata["email"]] = user
                print(f"Seeded user: {udata['email']} ({udata['role'].value})")
            else:
                user_records[udata["email"]] = existing
                print(f"User already exists: {udata['email']}")

        supervisor = user_records.get("supervisor@mundus.org")

        now = datetime.now(timezone.utc)
        demo_dump_points = [
            {
                "name": "Nwaniba Road Dump Point",
                "latitude": 5.0378,
                "longitude": 7.9128,
                "assigned_contractor_id": "CTR-AK-001",
                "assigned_supervisor_id": supervisor.id if supervisor else None,
                "interval_days": 7,
                "last_clearance_timestamp": now - timedelta(days=2),  # Recent clearance (Clean)
            },
            {
                "name": "IBB Way Central Evacuation Hub",
                "latitude": 5.0245,
                "longitude": 7.9281,
                "assigned_contractor_id": "CTR-AK-001",
                "assigned_supervisor_id": supervisor.id if supervisor else None,
                "interval_days": 7,
                "last_clearance_timestamp": now - timedelta(days=12),  # Pre-flagged Overdue!
            },
            {
                "name": "Oron Road Market Collector",
                "latitude": 5.0312,
                "longitude": 7.9354,
                "assigned_contractor_id": "CTR-AK-002",
                "assigned_supervisor_id": supervisor.id if supervisor else None,
                "interval_days": 7,
                "last_clearance_timestamp": now - timedelta(days=15),  # Pre-flagged Overdue!
            },
            {
                "name": "Plaza Commercial Waste Site",
                "latitude": 5.0410,
                "longitude": 7.9215,
                "assigned_contractor_id": "CTR-AK-001",
                "assigned_supervisor_id": supervisor.id if supervisor else None,
                "interval_days": 7,
                "last_clearance_timestamp": now - timedelta(days=4),  # Clean
            },
            {
                "name": "Aka Road Junction Collector",
                "latitude": 5.0198,
                "longitude": 7.9180,
                "assigned_contractor_id": "CTR-AK-002",
                "assigned_supervisor_id": supervisor.id if supervisor else None,
                "interval_days": 7,
                "last_clearance_timestamp": None,  # Never cleared site
            },
        ]

        for dp_data in demo_dump_points:
            existing_dp = db.query(DumpPoint).filter(DumpPoint.name == dp_data["name"]).first()
            if not existing_dp:
                dp = DumpPoint(**dp_data)
                db.add(dp)
                print(f"Seeded dump point: {dp_data['name']}")
            else:
                print(f"Dump point already exists: {dp_data['name']}")

        db.commit()
        print("Database seed completed successfully!")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
