from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field, ConfigDict
from app.payouts.models import PayoutStatus


class ContractorPayoutDetailsUpdate(BaseModel):
    monthly_stipend: float = Field(..., ge=0, description="Monthly fixed stipend in NGN")
    bank_account_number: str = Field(..., min_length=10, max_length=10, description="10-digit NUBAN account number")
    bank_code: str = Field(..., min_length=2, max_length=10, description="CBN 3-digit bank sort code")
    bank_name: str | None = Field(None, description="Commercial bank name")
    bank_account_name: str | None = Field(None, description="Account holder name")


class ContractorPayoutDetailsResponse(BaseModel):
    contractor_id: str
    name: str
    email: str
    monthly_stipend: float
    bank_name: str | None = None
    bank_account_number: str | None = None
    bank_account_name: str | None = None
    bank_code: str | None = None
    payment_provider_recipient_id: str | None = None
    is_payout_ready: bool = False

    model_config = ConfigDict(from_attributes=True)


class PayoutStatementResponse(BaseModel):
    id: str
    contractor_id: str
    contractor_name: str | None = None
    contractor_email: str | None = None
    period: str
    monthly_stipend: float
    expected_clearances: int
    verified_clearances: int
    held_clearances: int
    calculated_payout_amount: float
    status: PayoutStatus
    unique_payout_reference: str
    transfer_code: str | None = None
    approved_by_id: int | None = None
    approved_by_name: str | None = None
    approved_at: datetime | None = None
    payment_provider: str = "bachs"
    payment_provider_status: str | None = None
    failure_reason: str | None = None
    calculation_breakdown: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PayoutStatementListResponse(BaseModel):
    period: str | None = None
    total_stipend_pool: float = 0.0
    total_earned_amount: float = 0.0
    total_paid_amount: float = 0.0
    pending_approval_count: int = 0
    total_count: int = 0
    statements: list[PayoutStatementResponse] = []


class SiteClearanceBreakdown(BaseModel):
    site_id: str
    site_name: str
    code: str | None = None
    interval_days: int
    expected_clearances: int
    verified_clearances: int
    held_clearances: int


class ContractorProgressiveEarningsResponse(BaseModel):
    contractor_id: str
    contractor_name: str
    period: str
    days_in_month: int
    monthly_stipend: float
    expected_clearances: int
    verified_clearances: int
    held_clearances: int
    earned_so_far: float
    progress_percent: float
    sites_breakdown: list[SiteClearanceBreakdown] = []
    payout_statement: PayoutStatementResponse | None = None


class PayoutApprovalRequest(BaseModel):
    notes: str | None = None


class PayoutBulkApprovalRequest(BaseModel):
    period: str
    statement_ids: list[str] | None = None
    notes: str | None = None


class HeldClearanceItem(BaseModel):
    site_id: str
    site_name: str
    date: str
    contractor_id: str | None = None
    contractor_name: str | None = None
    before_check_in_id: int | None = None
    after_check_in_id: int | None = None
    flags: list[str] = []
    reason: str = "Flagged visit held for agency review"


class BankItemResponse(BaseModel):
    name: str
    code: str


class BankResolveRequest(BaseModel):
    account_number: str = Field(..., min_length=10, max_length=10)
    bank_code: str = Field(..., min_length=2, max_length=10)


class BankResolveResponse(BaseModel):
    account_number: str
    account_name: str
    bank_code: str
    bank_name: str
