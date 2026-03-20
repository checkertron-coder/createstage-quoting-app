"""Add password_reset_tokens table for password reset and email verification.

Revision ID: e1f2a3b4c5d6
Revises: d9a1b3c5e7f2
Create Date: 2026-03-19
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers
revision = "e1f2a3b4c5d6"
down_revision = "d9a1b3c5e7f2"
branch_labels = None
depends_on = None


def _table_exists(table_name):
    """Check if a table exists (idempotent)."""
    bind = op.get_bind()
    insp = inspect(bind)
    return table_name in insp.get_table_names()


def upgrade() -> None:
    if not _table_exists("password_reset_tokens"):
        op.create_table(
            "password_reset_tokens",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("token_hash", sa.String(), nullable=False),
            sa.Column("token_type", sa.String(), server_default="reset"),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("used_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_password_reset_tokens_token_hash", "password_reset_tokens", ["token_hash"])
        op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])


def downgrade() -> None:
    if _table_exists("password_reset_tokens"):
        op.drop_table("password_reset_tokens")
