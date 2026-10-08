import enum
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, DateTime, Enum, ForeignKey, JSON, Text
from sqlalchemy.orm import relationship
from app.database import Base


class PayoutStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class PayoutStatement(Base):
    __tablename__ = "payout_statements"

    id = Column(String(36), primary_key=True, index=True, default=lambda: uuid.uuid4().hex)
    contractor_id = Column(String(36), ForeignKey("contractors.id"), nullable=False, index=True)
    period = Column(String(7), nullable=False, index=True)  # Format: "YYYY-MM" (e.g. "2026-10")

    # Snapshot of values for this period (immutable once generated/finalized)
    monthly_stipend = Column(Float, nullable=False, default=0.0)
    expected_clearances = Column(Integer, nullable=False, default=0)
    verified_clearances = Column(Integer, nullable=False, default=0)
    held_clearances = Column(Integer, nullable=False, default=0)
    calculated_payout_amount = Column(Float, nullable=False, default=0.0)

    # Status & References
    status = Column(Enum(PayoutStatus), default=PayoutStatus.PENDING_APPROVAL, nullable=False, index=True)
    unique_payout_reference = Column(String(100), unique=True, index=True, nullable=False)
    transfer_code = Column(String(100), nullable=True, index=True)  # Provider withdrawal ID (e.g. "pay_...")

    # Approval Information
    approved_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)

    # Payment Provider Details (Bachs)
    payment_provider = Column(String(50), default="bachs", nullable=False)
    payment_provider_status = Column(String(50), nullable=True)
    payment_provider_response = Column(JSON, default=dict, nullable=False)
    failure_reason = Column(String(500), nullable=True)
    audit_notes = Column(Text, nullable=True)

    # Calculation details snapshot (e.g., breakdown per site)
    calculation_breakdown = Column(JSON, default=dict, nullable=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    contractor = relationship("Contractor", foreign_keys=[contractor_id])
    approved_by = relationship("User", foreign_keys=[approved_by_id])


class PayoutAuditLog(Base):
    __tablename__ = "payout_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    statement_id = Column(String(36), ForeignKey("payout_statements.id"), nullable=False, index=True)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(100), nullable=False)
    from_status = Column(String(50), nullable=True)
    to_status = Column(String(50), nullable=True)
    details = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    statement = relationship("PayoutStatement", foreign_keys=[statement_id])
    actor = relationship("User", foreign_keys=[actor_id])


class WalletTopUp(Base):
    __tablename__ = "wallet_topups"

    id = Column(String(36), primary_key=True, default=lambda: uuid.uuid4().hex)
    reference = Column(String(100), unique=True, index=True, nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String(10), default="NGN", nullable=False)
    status = Column(String(50), default="pending", nullable=False)  # pending, completed, failed
    checkout_url = Column(String(500), nullable=True)
    session_id = Column(String(100), nullable=True)
    initiated_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    provider_response = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    initiated_by = relationship("User", foreign_keys=[initiated_by_id])

