"""add subscriptions for per-tenant billing state (Phase 10)

Revision ID: 022_add_subscriptions
Revises: 021_add_product_events
Create Date: 2026-07-12 00:00:00.000000

Run with: alembic upgrade head

Creates subscriptions (per-tenant plan/status/provider). Idempotent via an
inspector table check; coexists with create_all().
"""

from alembic import op
import sqlalchemy as sa

revision = "022_add_subscriptions"
down_revision = "021_add_product_events"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade():
    if _table_exists("subscriptions"):
        return
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), unique=True, nullable=False),
        sa.Column("plan", sa.String(), nullable=False, server_default="free"),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("provider", sa.String(), nullable=False, server_default="manual"),
        sa.Column("current_period_end", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )


def downgrade():
    if _table_exists("subscriptions"):
        op.drop_table("subscriptions")
