"""add audience column to notifications

Revision ID: 026_add_notification_audience
Revises: 025_add_notifications
Create Date: 2026-08-05 00:00:00.000000

Run with: alembic upgrade head

Notifications are read by every role, but their bodies are not uniformly safe to
show everyone (the morning briefing carries revenue). `audience` records who may
read each row, decided at emit time.

server_default="admin" is deliberate and fail-closed: any row written before this
column existed becomes owner-only rather than being widened by default. The
feature is days old, so this affects a handful of rows at most — and the safe
direction for an unclassified alert is restricted, not visible.
"""

from alembic import op
import sqlalchemy as sa

revision = "026_add_notification_audience"
down_revision = "025_add_notifications"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _table_exists(name: str) -> bool:
    return name in _insp().get_table_names()


def _column_exists(table: str, column: str) -> bool:
    return column in [c["name"] for c in _insp().get_columns(table)]


def upgrade():
    if _table_exists("notifications") and not _column_exists("notifications", "audience"):
        op.add_column(
            "notifications",
            sa.Column("audience", sa.String(), nullable=False, server_default="admin"),
        )


def downgrade():
    # Column drops are a no-op on SQLite, matching the pattern in 024.
    if _table_exists("notifications") and _column_exists("notifications", "audience"):
        op.drop_column("notifications", "audience")
