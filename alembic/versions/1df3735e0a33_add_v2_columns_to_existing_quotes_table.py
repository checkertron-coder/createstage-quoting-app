"""add v2 columns to existing quotes table

Revision ID: 1df3735e0a33
Revises: 82694c65cf42
Create Date: 2026-02-28 16:12:27.954581

Handles the case where the quotes table was created by Base.metadata.create_all()
before v2 columns were added to the ORM model. Adds missing columns idempotently.
Also creates bid_analyses table if missing.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = '1df3735e0a33'
down_revision: Union[str, None] = '82694c65cf42'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table_name, column_name):
    """Check if a column already exists in the table."""
    bind = op.get_bind()
    insp = inspect(bind)
    columns = [c["name"] for c in insp.get_columns(table_name)]
    return column_name in columns


def _table_exists(table_name):
    """Check if a table exists."""
    bind = op.get_bind()
    insp = inspect(bind)
    return table_name in insp.get_table_names()


def upgrade() -> None:
    # Add v2 columns to quotes table if they don't exist
    if _table_exists("quotes"):
        v2_columns = [
            ("user_id", sa.Integer(), True),
            ("session_id", sa.String(), True),
            ("inputs_json", sa.JSON(), True),
            ("outputs_json", sa.JSON(), True),
            ("selected_markup_pct", sa.Integer(), True),
            ("pdf_url", sa.String(), True),
        ]
        for col_name, col_type, nullable in v2_columns:
            if not _column_exists("quotes", col_name):
                op.add_column("quotes", sa.Column(col_name, col_type, nullable=nullable))

        # Add foreign key for user_id if column was just added
        # (skip FK constraint on existing data — it will apply to new rows)

    # Create bid_analyses table if it doesn't exist (added in Session 7)
    if not _table_exists("bid_analyses"):
        op.create_table(
            "bid_analyses",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("filename", sa.String(), nullable=True),
            sa.Column("page_count", sa.Integer(), nullable=True),
            sa.Column("extraction_confidence", sa.Float(), nullable=True),
            sa.Column("items_json", sa.JSON(), nullable=True),
            sa.Column("warnings_json", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )


def downgrade() -> None:
    # Remove v2 columns from quotes
    if _table_exists("quotes"):
        for col_name in ["pdf_url", "selected_markup_pct", "outputs_json",
                         "inputs_json", "session_id", "user_id"]:
            if _column_exists("quotes", col_name):
                op.drop_column("quotes", col_name)

    # Drop bid_analyses
    if _table_exists("bid_analyses"):
        op.drop_table("bid_analyses")
