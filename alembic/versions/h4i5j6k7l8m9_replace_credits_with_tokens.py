"""replace credits with token columns and model

Revision ID: h4i5j6k7l8m9
Revises: a3b4c5d6e7f8
Create Date: 2026-05-10 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'h4i5j6k7l8m9'
down_revision: Union[str, Sequence[str], None] = 'a3b4c5d6e7f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- daily_usage ---
    op.drop_constraint("uq_daily_usage_key_date", "daily_usage", type_="unique")
    op.drop_column("daily_usage", "credits")
    op.add_column("daily_usage", sa.Column("model", sa.String(100), nullable=False, server_default="unknown"))
    op.add_column("daily_usage", sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("daily_usage", sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"))
    op.create_unique_constraint("uq_daily_usage_key_date_model", "daily_usage", ["key_id", "date", "model"])

    # --- fallback_usage ---
    op.drop_constraint("uq_fallback_usage_orig_fb_month", "fallback_usage", type_="unique")
    op.drop_column("fallback_usage", "credits")
    op.add_column("fallback_usage", sa.Column("model", sa.String(100), nullable=False, server_default="unknown"))
    op.add_column("fallback_usage", sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("fallback_usage", sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"))
    op.create_unique_constraint("uq_fallback_usage_orig_fb_month_model", "fallback_usage", ["original_key_id", "fallback_key_id", "month", "model"])

    # --- gateway_key_daily_usage ---
    op.drop_constraint("uq_gw_daily_usage_gwkey_date_poolkey", "gateway_key_daily_usage", type_="unique")
    op.drop_column("gateway_key_daily_usage", "credits")
    op.add_column("gateway_key_daily_usage", sa.Column("model", sa.String(100), nullable=False, server_default="unknown"))
    op.add_column("gateway_key_daily_usage", sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("gateway_key_daily_usage", sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"))
    op.create_unique_constraint("uq_gw_daily_usage_gwkey_date_poolkey_model", "gateway_key_daily_usage", ["gateway_key_id", "date", "key_id", "model"])


def downgrade() -> None:
    # --- gateway_key_daily_usage ---
    op.drop_constraint("uq_gw_daily_usage_gwkey_date_poolkey_model", "gateway_key_daily_usage", type_="unique")
    op.drop_column("gateway_key_daily_usage", "output_tokens")
    op.drop_column("gateway_key_daily_usage", "input_tokens")
    op.drop_column("gateway_key_daily_usage", "model")
    op.add_column("gateway_key_daily_usage", sa.Column("credits", sa.Float(), nullable=False, server_default="0"))
    op.create_unique_constraint("uq_gw_daily_usage_gwkey_date_poolkey", "gateway_key_daily_usage", ["gateway_key_id", "date", "key_id"])

    # --- fallback_usage ---
    op.drop_constraint("uq_fallback_usage_orig_fb_month_model", "fallback_usage", type_="unique")
    op.drop_column("fallback_usage", "output_tokens")
    op.drop_column("fallback_usage", "input_tokens")
    op.drop_column("fallback_usage", "model")
    op.add_column("fallback_usage", sa.Column("credits", sa.Float(), nullable=False, server_default="0"))
    op.create_unique_constraint("uq_fallback_usage_orig_fb_month", "fallback_usage", ["original_key_id", "fallback_key_id", "month"])

    # --- daily_usage ---
    op.drop_constraint("uq_daily_usage_key_date_model", "daily_usage", type_="unique")
    op.drop_column("daily_usage", "output_tokens")
    op.drop_column("daily_usage", "input_tokens")
    op.drop_column("daily_usage", "model")
    op.add_column("daily_usage", sa.Column("credits", sa.Float(), nullable=False, server_default="0"))
    op.create_unique_constraint("uq_daily_usage_key_date", "daily_usage", ["key_id", "date"])
