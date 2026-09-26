from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class DumpPoint(Base):
    __tablename__ = "dump_points"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    code = Column(String(50), nullable=True, index=True)
    sector = Column(String(100), nullable=True)
    assigned_contractor_id = Column(String(100), nullable=True)
    assigned_supervisor_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    interval_days = Column(Integer, default=7, nullable=False)
    last_clearance_timestamp = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    assigned_supervisor = relationship("User", foreign_keys=[assigned_supervisor_id])
    check_ins = relationship("CheckIn", back_populates="site", cascade="all, delete-orphan")


