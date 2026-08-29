"""add reminder_sent_at column to reservations

Revision ID: 014_add_reservation_reminder_sent_at
Revises: 013_add_customer_feedback
Create Date: 2026-07-10 00:00:00.000000

Run with: alembic upgrade head

Records when a same-day reservation reminder was sent so the scheduled job is
idempotent within the day — a misfire/restart can't re-send. See
ai/whatsapp/brain.run_reservation_reminders. Idempotent via inspector check.
"""

from alembic import op
import sqlalchemy as sa

revision = "014_add_reservation_reminder_sent_at"
down_revision = "013_add_customer_feedback"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    return any(c["name"] == column_name for c in sa.inspect(op.get_bind()).get_columns(table_name))


def upgrade() -> None:
    if not _column_exists("reservations", "reminder_sent_at"):
        op.add_column("reservations", sa.Column("reminder_sent_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    if _column_exists("reservations", "reminder_sent_at"):
        with op.batch_alter_table("reservations") as batch_op:
            batch_op.drop_column("reminder_sent_at")