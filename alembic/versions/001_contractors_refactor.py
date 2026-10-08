"""Contractors refactor, supervisor to contractor role migration, and payouts schema

Revision ID: 001_contractors_refactor
Revises: 
Create Date: 2026-10-08 18:36:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = '001_contractors_refactor'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = inspect(conn)
    existing_tables = insp.get_table_names()

    # 1. Users table
    if "users" in existing_tables:
        u_cols = [c["name"] for c in insp.get_columns("users")]
        if "is_agency_staff" not in u_cols:
            op.add_column("users", sa.Column("is_agency_staff", sa.Boolean(), server_default=sa.text("false"), nullable=False))
        if "invited_by_id" not in u_cols:
            op.add_column("users", sa.Column("invited_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True))
        
        # Convert users.role: supervisor -> contractor
        if conn.dialect.name == "postgresql":
            conn.execute(sa.text("UPDATE users SET role = 'CONTRACTOR' WHERE role::text ILIKE 'supervisor';"))
        else:
            conn.execute(sa.text("UPDATE users SET role = 'contractor' WHERE LOWER(role) = 'supervisor';"))

    # 2. Contractors table
    if "contractors" in existing_tables:
        c_cols = [c["name"] for c in insp.get_columns("contractors")]
        if "email" not in c_cols:
            op.add_column("contractors", sa.Column("email", sa.String(length=255), nullable=True))
            if "supervisor_email" in c_cols:
                conn.execute(sa.text("UPDATE contractors SET email = supervisor_email WHERE email IS NULL OR email = '';"))
        if "user_id" not in c_cols:
            op.add_column("contractors", sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True))
            if "supervisor_user_id" in c_cols:
                conn.execute(sa.text("UPDATE contractors SET user_id = supervisor_user_id WHERE user_id IS NULL;"))
        if "monthly_stipend" not in c_cols:
            op.add_column("contractors", sa.Column("monthly_stipend", sa.Float(), server_default=sa.text("0.0"), nullable=False))
        if "bank_name" not in c_cols:
            op.add_column("contractors", sa.Column("bank_name", sa.String(length=100), nullable=True))
        if "bank_account_number" not in c_cols:
            op.add_column("contractors", sa.Column("bank_account_number", sa.String(length=20), nullable=True))
        if "bank_account_name" not in c_cols:
            op.add_column("contractors", sa.Column("bank_account_name", sa.String(length=255), nullable=True))
        if "bank_code" not in c_cols:
            op.add_column("contractors", sa.Column("bank_code", sa.String(length=10), nullable=True))
        if "payment_provider_recipient_id" not in c_cols:
            op.add_column("contractors", sa.Column("payment_provider_recipient_id", sa.String(length=100), nullable=True))
        if "payment_provider_metadata" not in c_cols:
            op.add_column("contractors", sa.Column("payment_provider_metadata", sa.JSON(), server_default=sa.text("'{}'"), nullable=False))

    # 3. Dump points table
    if "dump_points" in existing_tables:
        dp_cols = [c["name"] for c in insp.get_columns("dump_points")]
        if "code" not in dp_cols:
            op.add_column("dump_points", sa.Column("code", sa.String(length=50), nullable=True))
        if "sector" not in dp_cols:
            op.add_column("dump_points", sa.Column("sector", sa.String(length=100), nullable=True))
        if "interval_days" not in dp_cols:
            op.add_column("dump_points", sa.Column("interval_days", sa.Integer(), server_default=sa.text("7"), nullable=False))
        if "last_clearance_timestamp" not in dp_cols:
            op.add_column("dump_points", sa.Column("last_clearance_timestamp", sa.DateTime(timezone=True), nullable=True))

    # 4. Check-ins table
    if "check_ins" in existing_tables:
        ci_cols = [c["name"] for c in insp.get_columns("check_ins")]
        if "user_id" not in ci_cols:
            op.add_column("check_ins", sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True))
            if "supervisor_id" in ci_cols:
                conn.execute(sa.text("UPDATE check_ins SET user_id = supervisor_id WHERE user_id IS NULL;"))
            op.alter_column("check_ins", "user_id", nullable=False)

    # 5. Reporter flags table
    if "reporter_flags" in existing_tables:
        rf_cols = [c["name"] for c in insp.get_columns("reporter_flags")]
        if "reporter_community_id" not in rf_cols:
            op.add_column("reporter_flags", sa.Column("reporter_community_id", sa.Integer(), nullable=True))
        if "reporter_name" not in rf_cols:
            op.add_column("reporter_flags", sa.Column("reporter_name", sa.String(length=255), nullable=True))
        if "photo_url" not in rf_cols:
            op.add_column("reporter_flags", sa.Column("photo_url", sa.String(length=500), nullable=True))

    # 6. Payout statements table
    if "payout_statements" not in existing_tables:
        op.create_table(
            "payout_statements",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("contractor_id", sa.String(length=36), sa.ForeignKey("contractors.id"), nullable=False),
            sa.Column("period", sa.String(length=7), nullable=False),
            sa.Column("monthly_stipend", sa.Float(), nullable=False),
            sa.Column("expected_clearances", sa.Integer(), nullable=False),
            sa.Column("verified_clearances", sa.Integer(), nullable=False),
            sa.Column("held_clearances", sa.Integer(), nullable=False),
            sa.Column("calculated_payout_amount", sa.Float(), nullable=False),
            sa.Column("status", sa.String(length=16), server_default="DRAFT", nullable=False),
            sa.Column("unique_payout_reference", sa.String(length=100), unique=True, nullable=True),
            sa.Column("transfer_code", sa.String(length=100), nullable=True),
            sa.Column("approved_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("payment_provider", sa.String(length=50), server_default="bachs", nullable=False),
            sa.Column("payment_provider_status", sa.String(length=50), nullable=True),
            sa.Column("payment_provider_response", sa.JSON(), nullable=True),
            sa.Column("failure_reason", sa.String(length=500), nullable=True),
            sa.Column("audit_notes", sa.Text(), nullable=True),
            sa.Column("calculation_breakdown", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )

    # 7. Payout audit logs table
    if "payout_audit_logs" not in existing_tables:
        op.create_table(
            "payout_audit_logs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("statement_id", sa.String(length=36), sa.ForeignKey("payout_statements.id"), nullable=False),
            sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("action", sa.String(length=50), nullable=False),
            sa.Column("from_status", sa.String(length=20), nullable=True),
            sa.Column("to_status", sa.String(length=20), nullable=False),
            sa.Column("details", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )


def downgrade() -> None:
    pass
