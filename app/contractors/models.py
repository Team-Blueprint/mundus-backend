import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Float, JSON
from sqlalchemy.orm import relationship
from app.database import Base


class Contractor(Base):
    __tablename__ = "contractors"

    id = Column(String(36), primary_key=True, index=True, default=lambda: uuid.uuid4().hex)
    name = Column(String(255), unique=True, index=True, nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Monthly Stipend & Payment Provider (Bachs) Details
    monthly_stipend = Column(Float, default=0.0, nullable=False)
    bank_name = Column(String(100), nullable=True)
    bank_account_number = Column(String(20), nullable=True)
    bank_account_name = Column(String(255), nullable=True)
    bank_code = Column(String(10), nullable=True)
    payment_provider_recipient_id = Column(String(100), nullable=True)
    payment_provider_metadata = Column(JSON, default=dict, nullable=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", foreign_keys=[user_id])


class ContractorAlert(Base):
    __tablename__ = "contractor_alerts"

    id = Column(Integer, primary_key=True, index=True)
    site_id = Column(String(36), ForeignKey("dump_points.id"), nullable=False, index=True)
    contractor_id = Column(String(36), ForeignKey("contractors.id"), nullable=True, index=True)
    message = Column(String(500), nullable=False)
    is_seen = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    site = relationship("DumpPoint")
    contractor = relationship("Contractor", foreign_keys=[contractor_id])
