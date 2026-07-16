"""add support_tickets + support_ticket_messages (in-app staff support system)

Revision ID: 032_add_support_tickets
Revises: 031_add_notifications_and_push
Create Date: 2026-07-16 00:00:00.000000

Run with: alembic upgrade head

In-app support ticketing so staff have a way to raise an issue that doesn't
depend on the (currently unfunded) Twilio/WhatsApp channel — any dashboard
user can open a ticket, OWNER/MANAGER triage it, and both directions notify
through the same notifications table added in 031.

Idempotent via inspector checks; coexists with create_all().
"""

from alembic import op
import sqlalchemy as sa

revision = "032_add_support_tickets"
down_revision = "031_add_notifications_and_push"
branch_labels = None
depends_on = None

STATUS_VALUES = ("OPEN", "IN_PROGRESS", "RESOLVED", "CLOSED")


def _insp():
    return sa.inspect(op.get_bind())


def _table_exists(name: str) -> bool:
    return name in _insp().get_table_names()


def upgrade():
    if not _table_exists("support_tickets"):
        status_enum = sa.Enum(*STATUS_VALUES, name="supportticketstatus")
        status_enum.create(op.get_bind(), checkfirst=True)
        op.create_table(
            "support_tickets",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id"), nullable=False),
            sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("subject", sa.String(), nullable=False),
            sa.Column("status", status_enum, nullable=False, server_default="OPEN"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_support_tickets_restaurant_status", "support_tickets",
                         ["restaurant_id", "status"])

    if not _table_exists("support_ticket_messages"):
        op.create_table(
            "support_ticket_messages",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("ticket_id", sa.Integer(),
                      sa.ForeignKey("support_tickets.id", ondelete="CASCADE"), nullable=False),
            sa.Column("sender_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_support_ticket_messages_ticket", "support_ticket_messages", ["ticket_id"])


def downgrade():
    if _table_exists("support_ticket_messages"):
        op.drop_table("support_ticket_messages")
    if _table_exists("support_tickets"):
        op.drop_table("support_tickets")
        sa.Enum(name="supportticketstatus").drop(op.get_bind(), checkfirst=True)
