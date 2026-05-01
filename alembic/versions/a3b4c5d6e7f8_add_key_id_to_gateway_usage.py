"""add key_id to gateway usage tables

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-05-01 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'a3b4c5d6e7f8'
down_revision: Union[str, Sequence[str], None] = 'f2a3b4c5d6e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('gateway_key_daily_usage', sa.Column('key_id', sa.Integer(), sa.ForeignKey('api_keys.id'), nullable=True))
    op.drop_constraint('uq_gw_daily_usage_key_date', 'gateway_key_daily_usage', type_='unique')
    op.create_unique_constraint('uq_gw_daily_usage_gwkey_date_poolkey', 'gateway_key_daily_usage', ['gateway_key_id', 'date', 'key_id'])
    op.create_index('ix_gw_daily_usage_key_id', 'gateway_key_daily_usage', ['key_id'])

    op.add_column('gateway_key_usage', sa.Column('key_id', sa.Integer(), sa.ForeignKey('api_keys.id'), nullable=True))
    op.drop_constraint('uq_gw_key_usage_key_month', 'gateway_key_usage', type_='unique')
    op.create_unique_constraint('uq_gw_key_usage_gwkey_month_poolkey', 'gateway_key_usage', ['gateway_key_id', 'month', 'key_id'])


def downgrade() -> None:
    op.drop_constraint('uq_gw_key_usage_gwkey_month_poolkey', 'gateway_key_usage', type_='unique')
    op.drop_column('gateway_key_usage', 'key_id')
    op.create_unique_constraint('uq_gw_key_usage_key_month', 'gateway_key_usage', ['gateway_key_id', 'month'])

    op.drop_index('ix_gw_daily_usage_key_id', table_name='gateway_key_daily_usage')
    op.drop_constraint('uq_gw_daily_usage_gwkey_date_poolkey', 'gateway_key_daily_usage', type_='unique')
    op.drop_column('gateway_key_daily_usage', 'key_id')
    op.create_unique_constraint('uq_gw_daily_usage_key_date', 'gateway_key_daily_usage', ['gateway_key_id', 'date'])
