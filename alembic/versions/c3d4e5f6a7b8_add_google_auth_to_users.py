"""add google_id and email to users

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-04-27 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('google_id', sa.String(255), nullable=True))
    op.add_column('users', sa.Column('email', sa.String(255), nullable=True))
    op.create_unique_constraint('uq_users_google_id', 'users', ['google_id'])
    op.create_index('ix_users_google_id', 'users', ['google_id'])


def downgrade() -> None:
    op.drop_index('ix_users_google_id', table_name='users')
    op.drop_constraint('uq_users_google_id', 'users', type_='unique')
    op.drop_column('users', 'email')
    op.drop_column('users', 'google_id')
