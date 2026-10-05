import sys
import os
import uuid
from datetime import datetime, timedelta, timezone

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import engine, Base, SessionLocal
from app.auth.models import User, UserRole
import app.check_ins.models  # noqa
import app.reporters.models  # noqa
import app.contractors.models  # noqa
import app.agency.models  # noqa
import app.notifications.models  # noqa
from app.dump_points.models import DumpPoint
from app.contractors.models import Contractor, ContractorAlert
from app.reporters.models import Reporter, ReporterFlag, ReporterStatus
from app.core.security import get_password_hash
from app.check_ins.models import CheckIn, CheckInType, CheckInStatus


def migrate_db_columns(db: SessionLocal):
    from sqlalchemy import text
    if engine.dialect.name != "sqlite":
        return
    try:
        with engine.connect() as conn:
            # Recreate tables or add columns if needed
            # In a real app we'd use Alembic, but since this is a local seed, we can just rely on Base.metadata.create_all
            pass
    except Exception as e:
        print(f"Migration check notice: {e}")


def seed(db: SessionLocal = None):
    print("Creating database tables...")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True
    try:
        migrate_db_columns(db)

        demo_users = [
            {
                "email": "supervisor@mundus.org",
                "password": "Password123!",
                "full_name": "Emmanuel Udo",
                "role": UserRole.CONTRACTOR,
            },
            {
                "email": "blessing@mundus.org",
                "password": "Password123!",
                "full_name": "Blessing Akpan",
                "role": UserRole.CONTRACTOR,
            },
            {
                "email": "bassey@mundus.org",
                "password": "Password123!",
                "full_name": "Bassey Okon",
                "role": UserRole.CONTRACTOR,
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

        emmanuel = user_records.get("supervisor@mundus.org")
        blessing = user_records.get("blessing@mundus.org")
        bassey = user_records.get("bassey@mundus.org")

        # Seed Contractors
        demo_contractors = [
            {
                "id": uuid.uuid4().hex,
                "name": "CleanCity Services",
                "email": "supervisor@mundus.org",
                "user_id": emmanuel.id if emmanuel else None,
            },
            {
                "id": uuid.uuid4().hex,
                "name": "GreenPath Ltd",
                "email": "blessing@mundus.org",
                "user_id": blessing.id if blessing else None,
            },
            {
                "id": uuid.uuid4().hex,
                "name": "EcoWaste Management",
                "email": "bassey@mundus.org",
                "user_id": bassey.id if bassey else None,
            },
        ]

        contractor_records = {}
        for cdata in demo_contractors:
            existing_c = db.query(Contractor).filter(Contractor.name == cdata["name"]).first()
            if not existing_c:
                c = Contractor(**cdata)
                db.add(c)
                db.commit()
                db.refresh(c)
                contractor_records[cdata["name"]] = c
                print(f"Seeded contractor: {cdata['name']}")
            else:
                contractor_records[cdata["name"]] = existing_c

        clean_city = contractor_records.get("CleanCity Services")
        green_path = contractor_records.get("GreenPath Ltd")
        eco_waste = contractor_records.get("EcoWaste Management")

        now = datetime.now(timezone.utc)
        demo_dump_points = [
            {
                "id": uuid.uuid4().hex,
                "name": "Nwaniba Road Dump Point",
                "code": "AK-UYO-NWN-01",
                "sector": "Sector 4 · Uyo Urban Core",
                "latitude": 5.0378,
                "longitude": 7.9128,
                "assigned_contractor_id": clean_city.id if clean_city else None,
                "interval_days": 7,
                "last_clearance_timestamp": now - timedelta(days=14),
            },
            {
                "id": uuid.uuid4().hex,
                "name": "IBB Way Central Evacuation Hub",
                "code": "AK-UYO-IBB-02",
                "sector": "Sector 2 · Commercial Center",
                "latitude": 5.0245,
                "longitude": 7.9281,
                "assigned_contractor_id": green_path.id if green_path else None,
                "interval_days": 7,
                "last_clearance_timestamp": now - timedelta(days=12),
            },
            {
                "id": uuid.uuid4().hex,
                "name": "Oron Road Market Collector",
                "code": "AK-UYO-ORN-03",
                "sector": "Sector 3 · Market District",
                "latitude": 5.0312,
                "longitude": 7.9354,
                "assigned_contractor_id": clean_city.id if clean_city else None,
                "interval_days": 7,
                "last_clearance_timestamp": now - timedelta(days=11),
            },
            {
                "id": uuid.uuid4().hex,
                "name": "Plaza Commercial Waste Site",
                "code": "AK-UYO-PLZ-04",
                "sector": "Sector 1 · Plaza Central",
                "latitude": 5.0410,
                "longitude": 7.9215,
                "assigned_contractor_id": green_path.id if green_path else None,
                "interval_days": 7,
                "last_clearance_timestamp": now - timedelta(days=9),
            },
            {
                "id": uuid.uuid4().hex,
                "name": "Aka Road Junction Collector",
                "code": "AK-UYO-AKA-05",
                "sector": "Sector 5 · Aka Junction",
                "latitude": 5.0198,
                "longitude": 7.9180,
                "assigned_contractor_id": clean_city.id if clean_city else None,
                "interval_days": 7,
                "last_clearance_timestamp": now - timedelta(days=8),
            },
            {
                "id": uuid.uuid4().hex,
                "name": "Hospital Road Waste Terminal",
                "code": "AK-UYO-HSP-06",
                "sector": "Sector 6 · Health District",
                "latitude": 5.0300,
                "longitude": 7.9200,
                "assigned_contractor_id": clean_city.id if clean_city else None,
                "interval_days": 7,
                "last_clearance_timestamp": now - timedelta(days=3),
            },
            {
                "id": uuid.uuid4().hex,
                "name": "Market Square Evacuation Point",
                "code": "AK-UYO-MKT-07",
                "sector": "Sector 3 · Market District",
                "latitude": 5.0280,
                "longitude": 7.9250,
                "assigned_contractor_id": green_path.id if green_path else None,
                "interval_days": 7,
                "last_clearance_timestamp": now - timedelta(days=1),
            },
            {
                "id": uuid.uuid4().hex,
                "name": "Industrial Layout Dump Point",
                "code": "AK-UYO-IND-08",
                "sector": "Sector 7 · Industrial Area",
                "latitude": 5.0450,
                "longitude": 7.9100,
                "assigned_contractor_id": eco_waste.id if eco_waste else None,
                "interval_days": 7,
                "last_clearance_timestamp": now - timedelta(days=1),
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
                existing_dp.code = dp_data.get("code")
                existing_dp.sector = dp_data.get("sector")
                db.commit()
                dp_records[dp_data["name"]] = existing_dp

        nwaniba_site = dp_records.get("Nwaniba Road Dump Point")
        ibb_site = dp_records.get("IBB Way Central Evacuation Hub")

        # Seed Community Reporters
        if nwaniba_site:
            existing_rep = db.query(Reporter).filter(Reporter.phone == "08031234567").first()
            if not existing_rep:
                rep = Reporter(
                    name="Adaeze Okoro",
                    phone="08031234567",
                    site_id=nwaniba_site.id,
                    contractor_id=nwaniba_site.assigned_contractor_id,
                    status=ReporterStatus.APPROVED,
                    token="demo-reporter-nwaniba-123",
                )
                db.add(rep)
                print("Seeded approved reporter: Adaeze Okoro")

            # Seed a reporter flag
            rf_existing = db.query(ReporterFlag).filter(ReporterFlag.site_id == nwaniba_site.id).first()
            if not rf_existing:
                rf = ReporterFlag(
                    site_id=nwaniba_site.id,
                    reporter_name="Adaeze Okoro",
                    note="Overflowing waste at market entrance",
                    timestamp=now - timedelta(hours=2),
                )
                db.add(rf)
                print("Seeded reporter flag on Nwaniba Road Dump Point")

        # Seed Check-In
        if ibb_site and blessing:
            ci_existing = db.query(CheckIn).filter(CheckIn.site_id == ibb_site.id).first()
            if not ci_existing:
                ci = CheckIn(
                    site_id=ibb_site.id,
                    user_id=blessing.id,
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

        # Seed sample contractor alert
        if nwaniba_site and emmanuel:
            existing_alert = db.query(ContractorAlert).filter(ContractorAlert.site_id == nwaniba_site.id).first()
            if not existing_alert:
                alert = ContractorAlert(
                    site_id=nwaniba_site.id,
                    contractor_id=nwaniba_site.assigned_contractor_id,
                    message=f"{nwaniba_site.name} reported full by Adaeze Okoro",
                    is_seen=False,
                )
                db.add(alert)
                print("Seeded contractor alert for Nwaniba Road Dump Point")

        db.commit()
        print("Database seed completed successfully!")
    finally:
        if close_db:
            db.close()


if __name__ == "__main__":
    seed()
