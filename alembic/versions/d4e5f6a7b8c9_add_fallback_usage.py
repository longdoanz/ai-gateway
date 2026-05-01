"""add fallback_usage table

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-04-30 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'fallback_usage',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('original_key_id', sa.Integer(), nullable=False),
        sa.Column('fallback_key_id', sa.Integer(), nullable=False),
        sa.Column('month', sa.String(length=7), nullable=False),
        sa.Column('credits', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['original_key_id'], ['api_keys.id']),
        sa.ForeignKeyConstraint(['fallback_key_id'], ['api_keys.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('original_key_id', 'fallback_key_id', 'month', name='uq_fallback_usage_orig_fb_month'),
    )
    op.create_index('ix_fallback_usage_month', 'fallback_usage', ['month'])


def downgrade() -> None:
    op.drop_index('ix_fallback_usage_month', table_name='fallback_usage')
    op.drop_table('fallback_usage')
