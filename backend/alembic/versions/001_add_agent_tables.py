"""add pricing_recommendations and agent_messages

Revision ID: 001_add_agent_tables
Revises:
Create Date: 2024-01-01 00:00:00.000000

Run with: alembic upgrade head

Idempotent by design: models.py also defines these tables, and
database.init_db() (Base.metadata.create_all) may have already created them
before this migration runs. The deploy sequence is init_db() first (handles a
brand-new empty database, where these tables' FK targets — restaurants,
menu_items — don't exist yet for alembic to build against on its own), then
`alembic upgrade head` (adds the one thing create_all cannot express: the
partial unique index below). Every step here checks first via SQLAlchemy's
inspector rather than raw "IF NOT EXISTS" SQL, since ADD COLUMN/CREATE TABLE
IF NOT EXISTS isn't portable between SQLite (used in local dev/tests) and
Postgres (production), and a raw "INTEGER PRIMARY KEY" column wouldn't
autoincrement correctly on Postgres the way op.create_table's Integer/
primary_key=True does.
"""

from alembic import op
import sqlalchemy as sa

revision = "001_add_agent_tables"
down_revision = None
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _index_exists(table_name: str, index_name: str) -> bool:
    return any(idx["name"] == index_name for idx in sa.inspect(op.get_bind()).get_indexes(table_name))


def upgrade() -> None:
    # ── pricing_recommendations ──────────────────────────────────────────────
    if not _table_exists("pricing_recommendations"):
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
    if not _index_exists("pricing_recommendations", "ix_pricing_rec_id"):
        op.create_index("ix_pricing_rec_id", "pricing_recommendations", ["id"])
    if not _index_exists("pricing_recommendations", "ix_pricing_rec_restaurant_status"):
        op.create_index("ix_pricing_rec_restaurant_status", "pricing_recommendations", ["restaurant_id", "status"])
    if not _index_exists("pricing_recommendations", "ix_pricing_rec_item_status"):
        op.create_index("ix_pricing_rec_item_status", "pricing_recommendations", ["menu_item_id", "status"])

    # Partial unique index: only one PENDING recommendation per item per restaurant
    # at a time. This is the DB-level race condition guard (BUG 13 fix) — the one
    # thing create_all can never express, since it's not a plain SQLAlchemy Index.
    if not _index_exists("pricing_recommendations", "ix_pricing_rec_one_pending_per_item"):
        op.execute(
            """
            CREATE UNIQUE INDEX ix_pricing_rec_one_pending_per_item
            ON pricing_recommendations (restaurant_id, menu_item_id)
            WHERE status = 'PENDING'
            """
        )

    # ── agent_messages ───────────────────────────────────────────────────────
    if not _table_exists("agent_messages"):
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
    if not _index_exists("agent_messages", "ix_agent_messages_id"):
        op.create_index("ix_agent_messages_id", "agent_messages", ["id"])
    if not _index_exists("agent_messages", "ix_agent_messages_restaurant_created"):
        op.create_index("ix_agent_messages_restaurant_created", "agent_messages", ["restaurant_id", "created_at"])


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_pricing_rec_one_pending_per_item")
    op.drop_table("agent_messages")
    op.drop_table("pricing_recommendations")
