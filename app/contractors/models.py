from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class Contractor(Base):
    __tablename__ = "contractors"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, index=True, nullable=False)
    supervisor_name = Column(String(255), nullable=False)
    supervisor_email = Column(String(255), unique=True, index=True, nullable=False)
    supervisor_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    supervisor = relationship("User", foreign_keys=[supervisor_user_id])


class ContractorAlert(Base):
    __tablename__ = "contractor_alerts"

    id = Column(Integer, primary_key=True, index=True)
    site_id = Column(Integer, ForeignKey("dump_points.id"), nullable=False, index=True)
    supervisor_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    message = Column(String(500), nullable=False)
    is_seen = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    site = relationship("DumpPoint")
    supervisor = relationship("User", foreign_keys=[supervisor_id])
