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
    pass


def downgrade() -> None:
    pass
