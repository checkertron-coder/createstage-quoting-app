"""Add stripe_customer_id and stripe_subscription_id to users.

Revision ID: c7e2f4a8b1d6
Revises: b5d7e9f1a2c3
Create Date: 2026-03-16
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers
revision = "c7e2f4a8b1d6"
down_revision = "b5d7e9f1a2c3"
branch_labels = None
depends_on = None


def _column_exists(table_name, column_name):
    """Check if a column exists (idempotent)."""
    bind = op.get_bind()
    insp = inspect(bind)
    columns = [c["name"] for c in insp.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    if not _column_exists("users", "stripe_customer_id"):
        op.add_column("users", sa.Column("stripe_customer_id", sa.String(), nullable=True))
    if not _column_exists("users", "stripe_subscription_id"):
        op.add_column("users", sa.Column("stripe_subscription_id", sa.String(), nullable=True))


def downgrade() -> None:
    if _column_exists("users", "stripe_subscription_id"):
        op.drop_column("users", "stripe_subscription_id")
    if _column_exists("users", "stripe_customer_id"):
        op.drop_column("users", "stripe_customer_id")
