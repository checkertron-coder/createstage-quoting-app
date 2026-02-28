"""convert job_type columns from enum to varchar

Revision ID: 41c42a96763c
Revises: 1df3735e0a33
Create Date: 2026-02-28 16:35:50.217095

Production PostgreSQL may still have job_type as an ENUM type from the
original v1 schema. The v2 code writes values like "furniture_table" that
aren't in the old enum. This migration converts to VARCHAR and drops the
old enum type. Idempotent — safe to run on databases already using VARCHAR.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '41c42a96763c'
down_revision: Union[str, None] = '1df3735e0a33'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_enum_column(table_name, column_name):
    """Check if a column is using a PostgreSQL ENUM type (not VARCHAR)."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return False
    result = bind.execute(sa.text(
        "SELECT data_type, udt_name FROM information_schema.columns "
        "WHERE table_name = :table AND column_name = :col"
    ), {"table": table_name, "col": column_name})
    row = result.fetchone()
    if row is None:
        return False
    # USER-DEFINED means it's an ENUM (or composite type)
    return row[0] == "USER-DEFINED"


def _table_exists(table_name):
    """Check if a table exists."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return table_name in insp.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()

    # Only run raw SQL on PostgreSQL — SQLite uses VARCHAR already
    if bind.dialect.name != "postgresql":
        return

    # Convert quotes.job_type from ENUM to VARCHAR
    if _table_exists("quotes") and _is_enum_column("quotes", "job_type"):
        op.execute(sa.text(
            "ALTER TABLE quotes ALTER COLUMN job_type TYPE VARCHAR USING job_type::text"
        ))

    # Convert quote_sessions.job_type from ENUM to VARCHAR
    if _table_exists("quote_sessions") and _is_enum_column("quote_sessions", "job_type"):
        op.execute(sa.text(
            "ALTER TABLE quote_sessions ALTER COLUMN job_type TYPE VARCHAR USING job_type::text"
        ))

    # Drop the old enum type(s) — try common naming conventions
    # SQLAlchemy names enums lowercase: 'jobtype'
    # Some setups may use 'job_type' or 'JobType'
    for enum_name in ["jobtype", "job_type"]:
        op.execute(sa.text(f"DROP TYPE IF EXISTS {enum_name}"))


def downgrade() -> None:
    # No downgrade — converting back to enum would lose data for new v2 job types
    pass
