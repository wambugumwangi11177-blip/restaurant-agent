"""add last_alerted_at column to inventory_items

Revision ID: 010_add_inventory_last_alerted_at
Revises: 009_add_reservation_overlap_guard
Create Date: 2026-07-08 00:00:00.000000

Run with: alembic upgrade head

Per-item cooldown for stock alerts. `brain.run_stock_check` runs every 2 hours
during service (08:00-22:00 EAT) and, before this, re-alerted the owner about
the same low item on every single cycle — up to 7 identical WhatsApps a day, per
item, until someone restocked. Pricing recommendations already had a 7-day
cooldown; stock alerts had none.

NULL means "never alerted", so existing rows correctly alert once on the next
check. Idempotent via inspector check, matching migrations 006-008.
"""

from alembic import op
import sqlalchemy as sa

revision = "010_add_inventory_last_alerted_at"
down_revision = "009_add_reservation_overlap_guard"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    return any(c["name"] == column_name for c in sa.inspect(op.get_bind()).get_columns(table_name))


def upgrade() -> None:
    if not _column_exists("inventory_items", "last_alerted_at"):
        op.add_column("inventory_items", sa.Column("last_alerted_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("inventory_items") as batch_op:
        batch_op.drop_column("last_alerted_at")
