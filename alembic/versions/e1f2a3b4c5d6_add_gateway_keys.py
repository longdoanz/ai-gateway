"""add gateway_keys and can_create_gateway_key

Revision ID: e1f2a3b4c5d6
Revises: d4e5f6a7b8c9
Create Date: 2026-05-01 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('can_create_gateway_key', sa.Boolean(), nullable=False, server_default='false'))

    op.create_table(
        'gateway_keys',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('key_hash', sa.String(64), nullable=False),
        sa.Column('key_prefix', sa.String(20), nullable=False),
        sa.Column('key_suffix', sa.String(10), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', name='uq_gateway_keys_user_id'),
    )
    op.create_index('ix_gateway_keys_key_hash', 'gateway_keys', ['key_hash'])

    op.create_table(
        'gateway_key_usage',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('gateway_key_id', sa.Integer(), nullable=False),
        sa.Column('month', sa.String(7), nullable=False),
        sa.Column('current_usage', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['gateway_key_id'], ['gateway_keys.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('gateway_key_id', 'month', name='uq_gw_key_usage_key_month'),
    )


def downgrade() -> None:
    op.drop_table('gateway_key_usage')
    op.drop_index('ix_gateway_keys_key_hash', table_name='gateway_keys')
    op.drop_table('gateway_keys')
    op.drop_column('users', 'can_create_gateway_key')
