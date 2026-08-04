"""add in-app notifications table

Revision ID: 025_add_notifications
Revises: 024_add_enterprise_hierarchy
Create Date: 2026-08-04 00:00:00.000000

Run with: alembic upgrade head

In-app delivery for owner alerts, which were previously WhatsApp/SMS-only and
therefore reached nobody on a deployment without a configured Twilio sender.
Idempotent and dialect-aware, matching migrations 015-024; coexists with
create_all().
"""

from alembic import op
import sqlalchemy as sa

revision = "025_add_notifications"
down_revision = "024_add_enterprise_hierarchy"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _table_exists(name: str) -> bool:
    return name in _insp().get_table_names()


def _index_exists(table: str, name: str) -> bool:
    return name in [i["name"] for i in _insp().get_indexes(table)]


def upgrade():
    if not _table_exists("notifications"):
        op.create_table(
            "notifications",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id"), nullable=False),
            sa.Column("category", sa.String(), nullable=False, server_default="general"),
            sa.Column("severity", sa.String(), nullable=False, server_default="info"),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("body", sa.Text(), nullable=False, server_default=""),
            sa.Column("link", sa.String(), server_default=""),
            sa.Column("read_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )

    if _table_exists("notifications"):
        # Both the feed ("this restaurant, newest first") and the unread badge
        # read on these two columns; without the index every dashboard poll is a
        # full scan of a table that grows with every alert ever raised.
        if not _index_exists("notifications", "ix_notifications_restaurant_created"):
            op.create_index(
                "ix_notifications_restaurant_created",
                "notifications", ["restaurant_id", "created_at"],
            )
        if not _index_exists("notifications", "ix_notifications_restaurant_id"):
            op.create_index("ix_notifications_restaurant_id", "notifications", ["restaurant_id"])


def downgrade():
    if _table_exists("notifications"):
        op.drop_table("notifications")
