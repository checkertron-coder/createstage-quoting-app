"""Add deposit_labor_pct and deposit_materials_pct to users.

Revision ID: d9a1b3c5e7f2
Revises: c7e2f4a8b1d6
Create Date: 2026-03-19
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers
revision = "d9a1b3c5e7f2"
down_revision = "c7e2f4a8b1d6"
branch_labels = None
depends_on = None


def _column_exists(table_name, column_name):
    """Check if a column exists (idempotent)."""
    bind = op.get_bind()
    insp = inspect(bind)
    columns = [c["name"] for c in insp.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    if not _column_exists("users", "deposit_labor_pct"):
        op.add_column("users", sa.Column("deposit_labor_pct", sa.Integer(),
                                          server_default="50", nullable=True))
    if not _column_exists("users", "deposit_materials_pct"):
        op.add_column("users", sa.Column("deposit_materials_pct", sa.Integer(),
                                          server_default="100", nullable=True))


def downgrade() -> None:
    if _column_exists("users", "deposit_materials_pct"):
        op.drop_column("users", "deposit_materials_pct")
    if _column_exists("users", "deposit_labor_pct"):
        op.drop_column("users", "deposit_labor_pct")
