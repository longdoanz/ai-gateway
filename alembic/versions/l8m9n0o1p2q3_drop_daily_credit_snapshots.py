"""drop daily_credit_snapshots table

The dashboard's Credit Consumption Trend chart (the only reader of this
table) has been replaced by a daily active-users chart; nothing writes or
reads daily_credit_snapshots anymore.

Revision ID: l8m9n0o1p2q3
Revises: k7l8m9n0p1q2
Create Date: 2026-09-18 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'l8m9n0o1p2q3'
down_revision: Union[str, Sequence[str], None] = 'k7l8m9n0p1q2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_credit_snapshot_date", table_name="daily_credit_snapshots")
    op.drop_table("daily_credit_snapshots")


def downgrade() -> None:
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
