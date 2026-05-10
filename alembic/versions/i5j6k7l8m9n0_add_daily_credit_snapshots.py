"""add daily_credit_snapshots table

Revision ID: i5j6k7l8m9n0
Revises: h4i5j6k7l8m9
Create Date: 2026-05-11 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'i5j6k7l8m9n0'
down_revision: Union[str, Sequence[str], None] = 'h4i5j6k7l8m9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "daily_credit_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("kiro_user_id", sa.String(255), nullable=False),
        sa.Column("date", sa.String(10), nullable=False),
        sa.Column("current_usage", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("kiro_user_id", "date", name="uq_credit_snapshot_user_date"),
    )
    op.create_index("ix_credit_snapshot_date", "daily_credit_snapshots", ["date"])


def downgrade() -> None:
    op.drop_index("ix_credit_snapshot_date", table_name="daily_credit_snapshots")
    op.drop_table("daily_credit_snapshots")
