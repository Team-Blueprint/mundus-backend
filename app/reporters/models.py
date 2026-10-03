import enum
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from app.database import Base


class ReporterStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVOKED = "revoked"


class Reporter(Base):
    __tablename__ = "reporters"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    phone = Column(String(20), nullable=False, index=True)
    site_id = Column(Integer, ForeignKey("dump_points.id"), nullable=False, index=True)
    contractor_id = Column(Integer, nullable=True)
    status = Column(Enum(ReporterStatus), default=ReporterStatus.PENDING, nullable=False, index=True)
    token = Column(String(64), unique=True, index=True, nullable=True)
    rejection_reason = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    site = relationship("DumpPoint")


class ReporterFlag(Base):
    __tablename__ = "reporter_flags"

    id = Column(Integer, primary_key=True, index=True)
    site_id = Column(Integer, ForeignKey("dump_points.id"), nullable=False, index=True)
    reporter_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    reporter_community_id = Column(Integer, ForeignKey("reporters.id"), nullable=True, index=True)
    reporter_name = Column(String(255), nullable=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    note = Column(String(500), nullable=True)
    photo_url = Column(String(500), nullable=True)  # evidence photo from reporter upload

    site = relationship("DumpPoint")
    reporter = relationship("User", foreign_keys=[reporter_id])
    reporter_community = relationship("Reporter", foreign_keys=[reporter_community_id])
