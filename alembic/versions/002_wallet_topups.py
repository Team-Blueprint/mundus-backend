"""Add wallet_topups table for Bachs in-app checkout top-ups

Revision ID: 002_wallet_topups
Revises: 001_contractors_refactor
Create Date: 2026-10-08 19:38:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = '002_wallet_topups'
down_revision: Union[str, None] = '001_contractors_refactor'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = inspect(conn)
    existing_tables = insp.get_table_names()

    if "wallet_topups" not in existing_tables:
        op.create_table(
            "wallet_topups",
            sa.Column("id", sa.String(length=36), nullable=False, primary_key=True),
            sa.Column("reference", sa.String(length=100), nullable=False),
            sa.Column("amount", sa.Float(), nullable=False),
            sa.Column("currency", sa.String(length=10), server_default="NGN", nullable=False),
            sa.Column("status", sa.String(length=50), server_default="pending", nullable=False),
            sa.Column("checkout_url", sa.String(length=500), nullable=True),
            sa.Column("session_id", sa.String(length=100), nullable=True),
            sa.Column("initiated_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("provider_response", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_wallet_topups_reference", "wallet_topups", ["reference"], unique=True)


def downgrade() -> None:
    conn = op.get_bind()
    insp = inspect(conn)
    existing_tables = insp.get_table_names()
    if "wallet_topups" in existing_tables:
        op.drop_table("wallet_topups")
