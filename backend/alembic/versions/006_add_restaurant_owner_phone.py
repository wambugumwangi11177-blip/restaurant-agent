"""add owner_phone column to restaurants

Revision ID: 006_add_restaurant_owner_phone
Revises: 005_add_token_usage_table
Create Date: 2026-07-07 00:00:00.000000

Run with: alembic upgrade head

Owner WhatsApp phone moves from the OWNER_PHONE_{restaurant_id} env-var
convention to a real column, so onboarding a restaurant no longer needs a
redeploy and inbound routing is a direct lookup instead of an O(n) env scan.
Env vars remain a fallback (see brain._owner_phone / webhooks resolution), so
this is backward compatible. Idempotent via inspector check.
"""

from alembic import op
import sqlalchemy as sa

revision = "006_add_restaurant_owner_phone"
down_revision = "005_add_token_usage_table"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    return any(c["name"] == column_name for c in sa.inspect(op.get_bind()).get_columns(table_name))


def upgrade() -> None:
    if not _column_exists("restaurants", "owner_phone"):
        op.add_column("restaurants", sa.Column("owner_phone", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("restaurants") as batch_op:
        batch_op.drop_column("owner_phone")
