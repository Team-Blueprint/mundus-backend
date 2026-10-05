import enum
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Enum, Boolean, DateTime, ForeignKey
from app.database import Base


class UserRole(str, enum.Enum):
    CONTRACTOR = "contractor"
    AGENCY = "agency"
    REPORTER = "reporter"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.CONTRACTOR)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    # Staff management fields (agency staff users only)
    is_agency_staff = Column(Boolean, default=False, nullable=False)
    invited_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)


class PasswordResetToken(Base):
    """Single-use, ~1h-expiry token for the public forgot-password flow."""
    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), index=True, nullable=False)
    token = Column(String(128), unique=True, index=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

