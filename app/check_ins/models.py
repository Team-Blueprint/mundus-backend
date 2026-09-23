import enum
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, DateTime, Enum, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.database import Base


class CheckInType(str, enum.Enum):
    BEFORE = "before"
    AFTER = "after"


class CheckInStatus(str, enum.Enum):
    VALID = "valid"
    LOCATION_MISMATCH = "location_mismatch"
    FLAGGED = "flagged"


class CheckIn(Base):
    __tablename__ = "check_ins"

    id = Column(Integer, primary_key=True, index=True)
    site_id = Column(Integer, ForeignKey("dump_points.id"), nullable=False, index=True)
    supervisor_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    type = Column(Enum(CheckInType), nullable=False)
    photo_url = Column(String(500), nullable=False)
    photo_hash = Column(String(64), nullable=False, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    distance_from_site_meters = Column(Float, nullable=False)
    device_timestamp = Column(DateTime, nullable=False)
    server_timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    status = Column(Enum(CheckInStatus), default=CheckInStatus.VALID, nullable=False)
    flags = Column(JSON, default=list, nullable=False)

    site = relationship("DumpPoint", back_populates="check_ins")
    supervisor = relationship("User", foreign_keys=[supervisor_id])

