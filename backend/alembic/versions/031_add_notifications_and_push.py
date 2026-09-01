"""add notifications + push_subscriptions (staff comms channel independent of Twilio)

Revision ID: 031_add_notifications_and_push
Revises: 030_add_staff_phone_unique
Create Date: 2026-07-16 00:00:00.000000

Run with: alembic upgrade head

Twilio is unfunded, so the entire staff-alert pipeline (stock alerts, custody
risk, late POs, no-shows, failed M-Pesa, agent failures) is currently going
nowhere — send_whatsapp_message no-ops without configured Twilio creds. This
adds a channel that costs nothing and needs no external account: an in-app
notification feed (notifications, always populated) plus optional Web Push
(push_subscriptions, best-effort). See ai/orchestrator/push_notifier.py.

Idempotent via table-existence checks; coexists with create_all() (matches
022_add_subscriptions.py's pattern — pure new tables, no ALTER of existing
ones, no Postgres-only branching needed).
"""

from alembic import op
import sqlalchemy as sa

revision = "031_add_notifications_and_push"
down_revision = "030_add_staff_phone_unique"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade():
    if not _table_exists("notifications"):
        op.create_table(
            "notifications",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("event_type", sa.String(), nullable=False),
            sa.Column("url", sa.String(), nullable=True),
            sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_notifications_user_unread", "notifications", ["user_id", "is_read"])
        op.create_index("ix_notifications_user_created", "notifications", ["user_id", "created_at"])

    if not _table_exists("push_subscriptions"):
        op.create_table(
            "push_subscriptions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("endpoint", sa.String(), nullable=False, unique=True),
            sa.Column("p256dh", sa.String(), nullable=False),
            sa.Column("auth", sa.String(), nullable=False),
            sa.Column("user_agent", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_push_subscriptions_user", "push_subscriptions", ["user_id"])


def downgrade():
    if _table_exists("push_subscriptions"):
        op.drop_table("push_subscriptions")
    if _table_exists("notifications"):
        op.drop_table("notifications")
