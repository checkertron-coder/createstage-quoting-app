"""Add onboarding_complete to users + shop_equipment table.

Revision ID: f2a4c6d8e0b1
Revises: e1b3d5f7a9c2
Create Date: 2026-03-19
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers
revision = "f2a4c6d8e0b1"
down_revision = "e1b3d5f7a9c2"
branch_labels = None
depends_on = None


def _column_exists(table_name, column_name):
    bind = op.get_bind()
    insp = inspect(bind)
    columns = [c["name"] for c in insp.get_columns(table_name)]
    return column_name in columns


def _table_exists(table_name):
    bind = op.get_bind()
    insp = inspect(bind)
    return table_name in insp.get_table_names()


def upgrade() -> None:
    if not _column_exists("users", "onboarding_complete"):
        op.add_column("users", sa.Column("onboarding_complete", sa.Boolean(),
                                          server_default="0", nullable=True))

    if not _table_exists("shop_equipment"):
        op.create_table(
            "shop_equipment",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"),
                      unique=True, nullable=False),
            sa.Column("welding_processes", sa.JSON(), nullable=True),
            sa.Column("cutting_capabilities", sa.JSON(), nullable=True),
            sa.Column("forming_equipment", sa.JSON(), nullable=True),
            sa.Column("finishing_capabilities", sa.JSON(), nullable=True),
            sa.Column("raw_welding_answer", sa.Text(), nullable=True),
            sa.Column("raw_forming_answer", sa.Text(), nullable=True),
            sa.Column("raw_finishing_answer", sa.Text(), nullable=True),
            sa.Column("shop_notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        )


def downgrade() -> None:
    if _table_exists("shop_equipment"):
        op.drop_table("shop_equipment")
    if _column_exists("users", "onboarding_complete"):
        op.drop_column("users", "onboarding_complete")
