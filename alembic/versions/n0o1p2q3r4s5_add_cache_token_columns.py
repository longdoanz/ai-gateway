"""add cache_read_tokens / cache_creation_tokens to daily usage tables

Prompt-cache tokens (Anthropic cache_read/cache_creation_input_tokens, OpenAI
prompt_tokens_details.cached_tokens) were dropped by the 9router usage parser,
so a cached agent loop recorded ~16 input tokens per request. input_tokens
now holds the full prompt (cached included) and these columns break out the
cached part of it.

server_default '0' makes the ADD COLUMN metadata-only on Postgres 11+ (no
table rewrite); existing rows read as 0 cached tokens, which is what was
recorded for them.

Revision ID: n0o1p2q3r4s5
Revises: m9n0o1p2q3r4
Create Date: 2026-10-03 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'n0o1p2q3r4s5'
down_revision: Union[str, Sequence[str], None] = 'm9n0o1p2q3r4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ('gateway_key_daily_usage', 'service_account_daily_usage')
_COLUMNS = ('cache_read_tokens', 'cache_creation_tokens')


def upgrade() -> None:
    for table in _TABLES:
        for column in _COLUMNS:
            op.add_column(table, sa.Column(column, sa.BigInteger(), server_default='0', nullable=False))


def downgrade() -> None:
    for table in _TABLES:
        for column in _COLUMNS:
            op.drop_column(table, column)
