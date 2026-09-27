"""drop kiro_user_mappings table and api_keys.kiro_user_id

Removes the legacy bulk-imported "Kiro Users" mapping feature (Access tab /
import UI, now deleted) along with the api_keys.kiro_user_id column that
linked to it. Confirmed via prod DB: 14 api_keys rows reference this column,
0 of them active, none used in 16+ days — safe to drop with no data-preservation
step.

Revision ID: m9n0o1p2q3r4
Revises: l8m9n0o1p2q3
Create Date: 2026-09-27 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'm9n0o1p2q3r4'
down_revision: Union[str, Sequence[str], None] = 'l8m9n0o1p2q3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint('api_keys_kiro_user_id_fkey', 'api_keys', type_='foreignkey')
    op.drop_column('api_keys', 'kiro_user_id')
    op.drop_index('ix_kiro_user_mappings_kiro_user_id', table_name='kiro_user_mappings')
    op.drop_table('kiro_user_mappings')


def downgrade() -> None:
    op.create_table(
        'kiro_user_mappings',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('kiro_user_id', sa.String(length=255), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('username', sa.String(length=255), nullable=True),
        sa.Column('imported_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_kiro_user_mappings_kiro_user_id', 'kiro_user_mappings', ['kiro_user_id'], unique=True)
    op.add_column('api_keys', sa.Column('kiro_user_id', sa.String(length=255), nullable=True))
    op.create_foreign_key(
        'api_keys_kiro_user_id_fkey', 'api_keys', 'kiro_user_mappings', ['kiro_user_id'], ['kiro_user_id']
    )
