"""add subscription fields and invite_codes table

Revision ID: a3f8b2c1d4e5
Revises: 41c42a96763c
Create Date: 2026-03-16

Adds subscription/billing fields to users table and creates invite_codes table.
Idempotent — safe to run on databases that already have these columns.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = 'a3f8b2c1d4e5'
down_revision = '41c42a96763c'
branch_labels = None
depends_on = None


def _column_exists(table_name, column_name):
    """Check if a column already exists (idempotent migrations)."""
    bind = op.get_bind()
    insp = inspect(bind)
    columns = [c["name"] for c in insp.get_columns(table_name)]
    return column_name in columns


def _table_exists(table_name):
    """Check if a table already exists."""
    bind = op.get_bind()
    insp = inspect(bind)
    return table_name in insp.get_table_names()


def upgrade() -> None:
    # --- Add subscription fields to users table ---
    new_columns = {
        "subscription_status": sa.Column("subscription_status", sa.String(), server_default="trial"),
        "trial_ends_at": sa.Column("trial_ends_at", sa.DateTime(), nullable=True),
        "invite_code_used": sa.Column("invite_code_used", sa.String(), nullable=True),
        "terms_accepted_at": sa.Column("terms_accepted_at", sa.DateTime(), nullable=True),
        "nda_accepted_at": sa.Column("nda_accepted_at", sa.DateTime(), nullable=True),
        "quotes_this_month": sa.Column("quotes_this_month", sa.Integer(), server_default="0"),
        "billing_cycle_start": sa.Column("billing_cycle_start", sa.DateTime(), nullable=True),
    }
    for col_name, col_def in new_columns.items():
        if not _column_exists("users", col_name):
            op.add_column("users", col_def)

    # Update tier default from 'basic' to 'free' for existing users
    # (non-destructive — just changes the default for new rows)

    # --- Create invite_codes table ---
    if not _table_exists("invite_codes"):
        op.create_table(
            "invite_codes",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("code", sa.String(), nullable=False, unique=True, index=True),
            sa.Column("tier", sa.String(), server_default="professional"),
            sa.Column("max_uses", sa.Integer(), nullable=True),
            sa.Column("uses", sa.Integer(), server_default="0"),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.Column("created_by", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("is_active", sa.Boolean(), server_default="true"),
        )


def downgrade() -> None:
    op.drop_table("invite_codes")
    for col in ["subscription_status", "trial_ends_at", "invite_code_used",
                "terms_accepted_at", "nda_accepted_at", "quotes_this_month",
                "billing_cycle_start"]:
        if _column_exists("users", col):
            op.drop_column("users", col)
