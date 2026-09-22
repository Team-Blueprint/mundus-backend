import enum
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Enum, Boolean, DateTime
from app.database import Base


class UserRole(str, enum.Enum):
    SUPERVISOR = "supervisor"
    AGENCY = "agency"
    REPORTER = "reporter"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.SUPERVISOR)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

