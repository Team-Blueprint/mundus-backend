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
from app.check_ins.models import CheckIn, CheckInType, CheckInStatus
from app.reporters.models import ReporterFlag


def seed(db: SessionLocal = None):
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)

    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True
    try:
        demo_users = [
            {
                "email": "supervisor@mundus.org",
                "password": "Password123!",
                "full_name": "Emmanuel Udo",
                "role": UserRole.SUPERVISOR,
            },
            {
                "email": "blessing@mundus.org",
                "password": "Password123!",
                "full_name": "Blessing Akpan",
                "role": UserRole.SUPERVISOR,
            },
            {
                "email": "bassey@mundus.org",
                "password": "Password123!",
                "full_name": "Bassey Okon",
                "role": UserRole.SUPERVISOR,
            },
            {
                "email": "agency@mundus.org",
                "password": "Password123!",
                "full_name": "State Agency Admin",
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

        emmanuel = user_records.get("supervisor@mundus.org")
        blessing = user_records.get("blessing@mundus.org")
        bassey = user_records.get("bassey@mundus.org")
        reporter = user_records.get("reporter@mundus.org")

        now = datetime.now(timezone.utc)
        demo_dump_points = [
            {
                "name": "Nwaniba Road Dump Point",
                "latitude": 5.0378,
                "longitude": 7.9128,
                "assigned_contractor_id": "CleanCity Services",
                "assigned_supervisor_id": emmanuel.id if emmanuel else None,
                "interval_days": 7,
                "last_clearance_timestamp": now - timedelta(days=14),  # Recent clearance (Clean)
            },
            {
                "name": "IBB Way Central Evacuation Hub",
                "latitude": 5.0245,
                "longitude": 7.9281,
                "assigned_contractor_id": "GreenPath Ltd",
                "assigned_supervisor_id": blessing.id if blessing else None,
                "interval_days": 7,
                "last_clearance_timestamp": now - timedelta(days=12),  # Pre-flagged Overdue!
            },
            {
                "name": "Oron Road Market Collector",
                "latitude": 5.0312,
                "longitude": 7.9354,
                "assigned_contractor_id": "CleanCity Services",
                "assigned_supervisor_id": bassey.id if bassey else None,
                "interval_days": 7,
                "last_clearance_timestamp": now - timedelta(days=11),  # Pre-flagged Overdue!
            },
            {
                "name": "Plaza Commercial Waste Site",
                "latitude": 5.0410,
                "longitude": 7.9215,
                "assigned_contractor_id": "GreenPath Ltd",
                "assigned_supervisor_id": emmanuel.id if emmanuel else None,
                "interval_days": 7,
                "last_clearance_timestamp": now - timedelta(days=9),  # Clean
            },
            {
                "name": "Aka Road Junction Collector",
                "latitude": 5.0198,
                "longitude": 7.9180,
                "assigned_contractor_id": "CleanCity Services",
                "assigned_supervisor_id": blessing.id if blessing else None,
                "interval_days": 7,
                "last_clearance_timestamp": now - timedelta(days=8),  # Overdue (7-10 days)
            },
            {
                "name": "Hospital Road Waste Terminal",
                "latitude": 5.0300,
                "longitude": 7.9200,
                "assigned_contractor_id": "CleanCity Services",
                "assigned_supervisor_id": emmanuel.id if emmanuel else None,
                "interval_days": 7,
                "last_clearance_timestamp": now - timedelta(days=3),  # On schedule (<7 days)
            },
            {
                "name": "Market Square Evacuation Point",
                "latitude": 5.0280,
                "longitude": 7.9250,
                "assigned_contractor_id": "GreenPath Ltd",
                "assigned_supervisor_id": blessing.id if blessing else None,
                "interval_days": 7,
                "last_clearance_timestamp": now - timedelta(days=1),  # On schedule (<7 days)
            },
            {
                "name": "Industrial Layout Dump Point",
                "latitude": 5.0450,
                "longitude": 7.9100,
                "assigned_contractor_id": "CleanCity Services",
                "assigned_supervisor_id": bassey.id if bassey else None,
                "interval_days": 7,
                "last_clearance_timestamp": now - timedelta(days=1),  # On schedule (<7 days)
  # Never cleared site
            },
        ]

        dp_records = {}
        for dp_data in demo_dump_points:
            existing_dp = db.query(DumpPoint).filter(DumpPoint.name == dp_data["name"]).first()
            if not existing_dp:
                dp = DumpPoint(**dp_data)
                db.add(dp)
                db.commit()
                db.refresh(dp)
                dp_records[dp_data["name"]] = dp
                print(f"Seeded dump point: {dp_data['name']}")
            else:
                dp_records[dp_data["name"]] = existing_dp
                print(f"Dump point already exists: {dp_data['name']}")
         # Seed a reporter flag on Nwaniba Road Dump Point
        nwaniba_site = dp_records.get("Nwaniba Road Dump Point")
        if nwaniba_site and reporter:
            rf_existing = db.query(ReporterFlag).filter(ReporterFlag.site_id == nwaniba_site.id).first()
            if not rf_existing:
                rf = ReporterFlag(
                    site_id=nwaniba_site.id,
                    reporter_id=reporter.id,
                    note="Overflowing waste at market entrance",
                    timestamp=now - timedelta(hours=2),
                )
                db.add(rf)
                print("Seeded reporter flag on Nwaniba Road Dump Point")

        # Seed a location mismatch check-in on IBB Way Central Evacuation Hub
        ibb_site = dp_records.get("IBB Way Central Evacuation Hub")
        if ibb_site and blessing:
            ci_existing = db.query(CheckIn).filter(CheckIn.site_id == ibb_site.id).first()
            if not ci_existing:
                ci = CheckIn(
                    site_id=ibb_site.id,
                    supervisor_id=blessing.id,
                    type=CheckInType.BEFORE,
                    photo_url="https://res.cloudinary.com/demo/image/upload/sample.jpg",
                    photo_hash="abc123hash456",
                    latitude=ibb_site.latitude + 0.0016,  # ~180m away
                    longitude=ibb_site.longitude + 0.0016,
                    distance_from_site_meters=180.0,
                    device_timestamp=now - timedelta(hours=3),
                    server_timestamp=now - timedelta(hours=3),
                    status=CheckInStatus.LOCATION_MISMATCH,
                    flags=["location_mismatch"],
                )
                db.add(ci)
                print("Seeded location mismatch check-in on IBB Way")

        db.commit()
        print("Database seed completed successfully!")
    finally:
        if close_db:
            db.close()


if __name__ == "__main__":
    seed()
