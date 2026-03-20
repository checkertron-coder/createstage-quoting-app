"""merge_migration_heads

Revision ID: 62a3a640df71
Revises: e1f2a3b4c5d6, f2a4c6d8e0b1
Create Date: 2026-03-19 23:06:37.637510

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '62a3a640df71'
down_revision: Union[str, None] = ('e1f2a3b4c5d6', 'f2a4c6d8e0b1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Backfill: set email_verified=True for all existing users who have
    # a password_hash. These users registered before email verification
    # existed and should not be locked out.
    from sqlalchemy import text
    conn = op.get_bind()
    conn.execute(text(
        "UPDATE users SET email_verified = 1 "
        "WHERE password_hash IS NOT NULL AND "
        "(email_verified IS NULL OR NOT email_verified)"
    ))


def downgrade() -> None:
    pass
