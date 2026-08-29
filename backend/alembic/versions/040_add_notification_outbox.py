"""notification outbox (audit remediation, Tier 2 item 5)

Revision ID: 040_add_notification_outbox
Revises: 039_add_cash_drawer_counts
Create Date: 2026-07-25 00:00:00.000000

Run with: alembic upgrade head

events/bus.py's emit() used to log-and-drop a failed handler call with no
persistence at all. This table records only the failed deliveries (not every
successful one, which stays purely in-process) so a scheduled sweep
(main.py's outbox_sweep job) can retry them. See models.py's
NotificationOutbox docstring.

Idempotent via inspector checks, coexists with a create_all()-seeded schema.
"""

from alembic import op
import sqlalchemy as sa

revision = "040_add_notification_outbox"
down_revision = "039_add_cash_drawer_counts"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _table_exists(name: str) -> bool:
    return name in _insp().get_table_names()


def upgrade():
    if not _table_exists("notification_outbox"):
        op.create_table(
            "notification_outbox",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("event_type", sa.String(), nullable=False),
            sa.Column("handler_name", sa.String(), nullable=False),
            sa.Column("payload", sa.Text(), nullable=False),
            sa.Column("status", sa.String(), nullable=False, server_default="pending"),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("last_attempt_at", sa.DateTime(), nullable=True),
        )
        op.create_index(
            "ix_notification_outbox_status_created", "notification_outbox",
            ["status", "created_at"],
        )


def downgrade():
    if _table_exists("notification_outbox"):
        op.drop_table("notification_outbox")
