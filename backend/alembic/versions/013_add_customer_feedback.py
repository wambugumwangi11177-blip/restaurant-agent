"""add customer_feedback table

Revision ID: 013_add_customer_feedback
Revises: 012_add_restaurant_owner_channel
Create Date: 2026-07-10 00:00:00.000000

Run with: alembic upgrade head

Captures a diner's 1–5 rating sent over the messaging channel (reply to a
receipt). Low ratings alert the owner for service recovery — see
ai/whatsapp/brain.handle_customer_message. Idempotent via inspector check.
"""

from alembic import op
import sqlalchemy as sa

revision = "013_add_customer_feedback"
down_revision = "012_add_restaurant_owner_channel"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if _table_exists("customer_feedback"):
        return
    op.create_table(
        "customer_feedback",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id"), nullable=False),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=True),
        sa.Column("customer_phone", sa.String(), server_default=""),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_customer_feedback_restaurant_created",
        "customer_feedback",
        ["restaurant_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_customer_feedback_restaurant_created", table_name="customer_feedback")
    op.drop_table("customer_feedback")
