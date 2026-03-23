"""Add nda_acceptances table and used_by_email to invite_codes

Revision ID: f2a4b6c8d0e1
Revises: e1f2a3b4c5d6
Create Date: 2026-03-23
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "f2a4b6c8d0e1"
down_revision = "62a3a640df71"
branch_labels = None
depends_on = None


def upgrade():
    # NDA acceptance table — no FK cascade, records survive user deletion
    op.create_table(
        "nda_acceptances",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(), nullable=False, index=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("ip_address", sa.String(), nullable=True),
        sa.Column("user_agent", sa.String(), nullable=True),
        sa.Column("nda_version", sa.String(), nullable=False, server_default="2026-03-16"),
        sa.Column("accepted_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Lock invite codes to first user
    op.add_column("invite_codes", sa.Column("used_by_email", sa.String(), nullable=True))


def downgrade():
    op.drop_column("invite_codes", "used_by_email")
    op.drop_table("nda_acceptances")
