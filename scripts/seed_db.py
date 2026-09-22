import sys
import os

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import engine, Base, SessionLocal
from app.auth.models import User, UserRole
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
                print(f"Seeded user: {udata['email']} ({udata['role'].value})")
            else:
                print(f"User already exists: {udata['email']}")

        db.commit()
        print("Database seed completed successfully!")
    finally:
        db.close()


if __name__ == "__main__":
    seed()

