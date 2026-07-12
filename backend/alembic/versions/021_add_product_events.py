"""add product_events for in-app product analytics (Phase 8)

Revision ID: 021_add_product_events
Revises: 020_add_user_mfa
Create Date: 2026-07-12 00:00:00.000000

Run with: alembic upgrade head

Creates product_events (feature-usage/funnel/retention events for the app's own
users). Idempotent via an inspector table check; coexists with create_all().
"""

from alembic import op
import sqlalchemy as sa

revision = "021_add_product_events"
down_revision = "020_add_user_mfa"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade():
    if _table_exists("product_events"):
        return
    op.create_table(
        "product_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("event_name", sa.String(), nullable=False),
        sa.Column("properties", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_product_events_tenant_name_created",
        "product_events",
        ["tenant_id", "event_name", "created_at"],
    )


def downgrade():
    if _table_exists("product_events"):
        op.drop_index("ix_product_events_tenant_name_created", table_name="product_events")
        op.drop_table("product_events")
