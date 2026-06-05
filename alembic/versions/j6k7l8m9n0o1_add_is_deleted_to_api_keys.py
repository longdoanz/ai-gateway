"""add_is_deleted_to_api_keys

Revision ID: j6k7l8m9n0o1
Revises: ec1fd13892db
Create Date: 2026-05-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'j6k7l8m9n0o1'
down_revision: Union[str, None] = 'ec1fd13892db'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('api_keys', sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    op.drop_column('api_keys', 'is_deleted')
