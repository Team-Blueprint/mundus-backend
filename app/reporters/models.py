from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class ReporterFlag(Base):
    __tablename__ = "reporter_flags"

    id = Column(Integer, primary_key=True, index=True)
    site_id = Column(Integer, ForeignKey("dump_points.id"), nullable=False, index=True)
    reporter_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    note = Column(String(500), nullable=True)

    site = relationship("DumpPoint")
    reporter = relationship("User", foreign_keys=[reporter_id])

