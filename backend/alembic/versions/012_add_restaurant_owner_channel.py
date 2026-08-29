"""add owner_channel column to restaurants

Revision ID: 012_add_restaurant_owner_channel
Revises: 011_reconcile_model_column_drift
Create Date: 2026-07-10 00:00:00.000000

Run with: alembic upgrade head

Adds the owner's preferred alert channel ("whatsapp" | "sms" | "both"). SMS is a
first-class channel here because a large share of Kenyan restaurant owners and
customers aren't on WhatsApp — see ai/whatsapp/twilio_client.send(channel=...).
Defaults to "whatsapp" so existing behaviour is unchanged. Idempotent via
inspector check.
"""

from alembic import op
import sqlalchemy as sa

revision = "012_add_restaurant_owner_channel"
down_revision = "011_reconcile_model_column_drift"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_context().bind
    return any(c["name"] == column_name for c in sa.inspect(bind).get_columns(table_name))


def upgrade() -> None:
    if not _column_exists("restaurants", "owner_channel"):
        op.add_column(
            "restaurants",
            sa.Column("owner_channel", sa.String(), nullable=True, server_default="'whatsapp'"),
        )


def downgrade() -> None:
    if _column_exists("restaurants", "owner_channel"):
        with op.batch_alter_table("restaurants") as batch_op:
            batch_op.drop_column("owner_channel")