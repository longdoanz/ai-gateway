"""add service accounts

Revision ID: k7l8m9n0p1q2
Revises: j6k7l8m9n0o1
Create Date: 2026-09-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'k7l8m9n0p1q2'
down_revision: Union[str, Sequence[str], None] = 'j6k7l8m9n0o1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'service_accounts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('allowed_models', sa.Text(), nullable=False, server_default='[]'),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='uq_service_accounts_name'),
    )
    op.create_index('ix_service_accounts_name', 'service_accounts', ['name'])

    op.create_table(
        'service_account_keys',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('service_account_id', sa.Integer(), nullable=False),
        sa.Column('key_hash', sa.String(length=64), nullable=False),
        sa.Column('key_prefix', sa.String(length=20), nullable=False),
        sa.Column('key_suffix', sa.String(length=10), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['service_account_id'], ['service_accounts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key_hash', name='uq_service_account_keys_key_hash'),
    )
    op.create_index('ix_service_account_keys_service_account_id', 'service_account_keys', ['service_account_id'])
    op.create_index('ix_service_account_keys_key_hash', 'service_account_keys', ['key_hash'])

    op.create_table(
        'service_account_usage',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('service_account_id', sa.Integer(), nullable=False),
        sa.Column('month', sa.String(length=7), nullable=False),
        sa.Column('current_usage', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['service_account_id'], ['service_accounts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('service_account_id', 'month', name='uq_sa_usage_sa_month'),
    )

    op.create_table(
        'service_account_daily_usage',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('service_account_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.String(length=10), nullable=False),
        sa.Column('model', sa.String(length=100), nullable=False, server_default='unknown'),
        sa.Column('input_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('output_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['service_account_id'], ['service_accounts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('service_account_id', 'date', 'model', name='uq_sa_daily_usage_sa_date_model'),
    )
    op.create_index('ix_sa_daily_usage_date', 'service_account_daily_usage', ['date'])


def downgrade() -> None:
    op.drop_index('ix_sa_daily_usage_date', table_name='service_account_daily_usage')
    op.drop_table('service_account_daily_usage')
    op.drop_table('service_account_usage')
    op.drop_index('ix_service_account_keys_key_hash', table_name='service_account_keys')
    op.drop_index('ix_service_account_keys_service_account_id', table_name='service_account_keys')
    op.drop_table('service_account_keys')
    op.drop_index('ix_service_accounts_name', table_name='service_accounts')
    op.drop_table('service_accounts')
