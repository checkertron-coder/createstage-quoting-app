"""Add email_verified to users + email_tokens table.

Revision ID: e1b3d5f7a9c2
Revises: d9a1b3c5e7f2
Create Date: 2026-03-19
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers
revision = "e1b3d5f7a9c2"
down_revision = "d9a1b3c5e7f2"
branch_labels = None
depends_on = None


def _column_exists(table_name, column_name):
    """Check if a column exists (idempotent)."""
    bind = op.get_bind()
    insp = inspect(bind)
    columns = [c["name"] for c in insp.get_columns(table_name)]
    return column_name in columns


def _table_exists(table_name):
    """Check if a table exists (idempotent)."""
    bind = op.get_bind()
    insp = inspect(bind)
    return table_name in insp.get_table_names()


def upgrade() -> None:
    # Add email_verified to users (default False — all existing users must verify)
    if not _column_exists("users", "email_verified"):
        op.add_column("users", sa.Column("email_verified", sa.Boolean(),
                                          server_default="0", nullable=True))

    # Create email_tokens table
    if not _table_exists("email_tokens"):
        op.create_table(
            "email_tokens",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("token", sa.String(), unique=True, nullable=False, index=True),
            sa.Column("token_type", sa.String(), nullable=False),
            sa.Column("is_used", sa.Boolean(), server_default="0"),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        )


def downgrade() -> None:
    if _table_exists("email_tokens"):
        op.drop_table("email_tokens")
    if _column_exists("users", "email_verified"):
        op.drop_column("users", "email_verified")
