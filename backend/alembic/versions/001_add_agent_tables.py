"""add pricing_recommendations and agent_messages

Revision ID: 001_add_agent_tables
Revises: 
Create Date: 2024-01-01 00:00:00.000000

Run with: alembic upgrade head
"""

from alembic import op
import sqlalchemy as sa

revision = "001_add_agent_tables"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── pricing_recommendations ──────────────────────────────────────────────
    op.create_table(
        "pricing_recommendations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id"), nullable=False),
        sa.Column("menu_item_id", sa.Integer(), sa.ForeignKey("menu_items.id"), nullable=False),
        sa.Column("recommendation_type", sa.String(), nullable=False),
        sa.Column("current_price", sa.Integer(), nullable=False),
        sa.Column("suggested_price", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True, server_default=""),
        sa.Column("when_to_apply", sa.String(), nullable=True, server_default="All times"),
        sa.Column("monthly_impact_cents", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("recommendation_strength", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("status", sa.String(), nullable=True, server_default="PENDING"),
        sa.Column("rejection_reason", sa.String(), nullable=True, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("actioned_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pricing_rec_id", "pricing_recommendations", ["id"])
    op.create_index("ix_pricing_rec_restaurant_status", "pricing_recommendations", ["restaurant_id", "status"])
    op.create_index("ix_pricing_rec_item_status", "pricing_recommendations", ["menu_item_id", "status"])

    # Partial unique index: only one PENDING recommendation per item per restaurant at a time
    # This is the DB-level race condition guard (BUG 13 fix)
    op.execute(
        """
        CREATE UNIQUE INDEX ix_pricing_rec_one_pending_per_item
        ON pricing_recommendations (restaurant_id, menu_item_id)
        WHERE status = 'PENDING'
        """
    )

    # ── agent_messages ───────────────────────────────────────────────────────
    op.create_table(
        "agent_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id"), nullable=False),
        sa.Column("recipient", sa.String(), nullable=False),
        sa.Column("message_body", sa.Text(), nullable=False),
        sa.Column("message_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("twilio_sid", sa.String(), nullable=True, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_messages_id", "agent_messages", ["id"])
    op.create_index("ix_agent_messages_restaurant_created", "agent_messages", ["restaurant_id", "created_at"])


def downgrade() -> None:
    op.drop_table("agent_messages")
    op.execute("DROP INDEX IF EXISTS ix_pricing_rec_one_pending_per_item")
    op.drop_table("pricing_recommendations")
