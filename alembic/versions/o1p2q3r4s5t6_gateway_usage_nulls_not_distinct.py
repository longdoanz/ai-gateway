"""merge duplicate gateway-key usage rows; UNIQUE ... NULLS NOT DISTINCT

The upserts on gateway_key_usage / gateway_key_daily_usage target UNIQUE
constraints that include the nullable key_id. 9router traffic always writes
key_id = NULL, and Postgres treats NULLs as distinct, so ON CONFLICT never
fired: every request inserted a fresh row (53k monthly rows for 275 real
buckets). Totals were still right — only the row count exploded.

This merges each bucket into its lowest-id row (sums of the counters,
latest last_used_at) and recreates both constraints as NULLS NOT DISTINCT
(Postgres 15+) so the upsert finally converges. The tables are locked for
the merge so a still-running old gateway cannot slip a duplicate in between.

Also widens the daily token columns to BIGINT: input_tokens now includes
cached prompt tokens (~100k per agent request) and would overflow int32.

Revision ID: o1p2q3r4s5t6
Revises: n0o1p2q3r4s5
Create Date: 2026-10-03 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'o1p2q3r4s5t6'
down_revision: Union[str, Sequence[str], None] = 'n0o1p2q3r4s5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_MONTHLY_KEYS = ('gateway_key_id', 'month', 'key_id')
_DAILY_KEYS = ('gateway_key_id', 'date', 'key_id', 'model')
_WIDENED_TABLES = ('gateway_key_daily_usage', 'service_account_daily_usage')


def _merge(table: str, keys: tuple[str, ...], aggregates: dict[str, str]) -> None:
    """Fold every duplicate bucket of ``table`` into its lowest-id row."""
    group_by = ', '.join(keys)
    select_aggs = ', '.join(f'{expr} AS {col}' for col, expr in aggregates.items())
    set_clause = ', '.join(f'{col} = agg.{col}' for col in aggregates)
    op.execute(f'LOCK TABLE {table} IN SHARE ROW EXCLUSIVE MODE')
    op.execute(
        f'UPDATE {table} SET {set_clause} '
        f'FROM (SELECT min(id) AS keep_id, {select_aggs} FROM {table} '
        f'GROUP BY {group_by} HAVING count(*) > 1) agg '
        f'WHERE {table}.id = agg.keep_id'
    )
    op.execute(
        f'DELETE FROM {table} WHERE id NOT IN (SELECT min(id) FROM {table} GROUP BY {group_by})'
    )


def upgrade() -> None:
    # Widen first so a merged sum can never overflow int32 on write.
    for table in _WIDENED_TABLES:
        for column in ('input_tokens', 'output_tokens'):
            op.alter_column(table, column, type_=sa.BigInteger(), existing_type=sa.Integer(), existing_nullable=False)

    _merge('gateway_key_usage', _MONTHLY_KEYS, {
        'current_usage': 'sum(current_usage)',
        'last_used_at': 'max(last_used_at)',
    })
    _merge('gateway_key_daily_usage', _DAILY_KEYS, {
        'input_tokens': 'sum(input_tokens::bigint)',
        'output_tokens': 'sum(output_tokens::bigint)',
        'cache_read_tokens': 'sum(cache_read_tokens)',
        'cache_creation_tokens': 'sum(cache_creation_tokens)',
        'created_at': 'min(created_at)',
    })

    op.drop_constraint('uq_gw_key_usage_gwkey_month_poolkey', 'gateway_key_usage', type_='unique')
    op.create_unique_constraint(
        'uq_gw_key_usage_gwkey_month_poolkey', 'gateway_key_usage', list(_MONTHLY_KEYS),
        postgresql_nulls_not_distinct=True,
    )
    op.drop_constraint('uq_gw_daily_usage_gwkey_date_poolkey_model', 'gateway_key_daily_usage', type_='unique')
    op.create_unique_constraint(
        'uq_gw_daily_usage_gwkey_date_poolkey_model', 'gateway_key_daily_usage', list(_DAILY_KEYS),
        postgresql_nulls_not_distinct=True,
    )


def downgrade() -> None:
    # The merge is not reversible (and need not be: sums are unchanged), and
    # the columns stay BIGINT — narrowing could fail on merged sums.
    op.drop_constraint('uq_gw_daily_usage_gwkey_date_poolkey_model', 'gateway_key_daily_usage', type_='unique')
    op.create_unique_constraint(
        'uq_gw_daily_usage_gwkey_date_poolkey_model', 'gateway_key_daily_usage', list(_DAILY_KEYS)
    )
    op.drop_constraint('uq_gw_key_usage_gwkey_month_poolkey', 'gateway_key_usage', type_='unique')
    op.create_unique_constraint(
        'uq_gw_key_usage_gwkey_month_poolkey', 'gateway_key_usage', list(_MONTHLY_KEYS)
    )
