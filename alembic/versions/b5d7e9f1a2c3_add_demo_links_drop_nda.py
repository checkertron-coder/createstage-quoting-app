"""Add demo_links table, drop nda_accepted_at from users.

Revision ID: b5d7e9f1a2c3
Revises: a3f8b2c1d4e5
Create Date: 2026-03-16
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "b5d7e9f1a2c3"
down_revision = "a3f8b2c1d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create demo_links table
    op.create_table(
        "demo_links",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("token", sa.String(), nullable=False, unique=True, index=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("label", sa.String(), nullable=True),
        sa.Column("tier", sa.String(), server_default="professional"),
        sa.Column("max_quotes", sa.Integer(), server_default="3"),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("is_used", sa.Boolean(), server_default="false"),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("demo_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # Drop nda_accepted_at from users (NDA gate removed in P53B)
    # Use batch mode for SQLite compatibility
    try:
        op.drop_column("users", "nda_accepted_at")
    except Exception:
        pass  # Column may not exist on fresh DBs


def downgrade() -> None:
    op.add_column("users", sa.Column("nda_accepted_at", sa.DateTime(), nullable=True))
    op.drop_table("demo_links")
