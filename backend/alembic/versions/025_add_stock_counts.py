"""add stock_counts table (shrinkage detection)

Revision ID: 025_add_stock_counts
Revises: 024_add_enterprise_hierarchy
Create Date: 2026-08-06 00:00:00.000000

Run with: alembic upgrade head

Physical stock counts compared against the theoretical usage stock_ledger.py
already tracks (recipes x orders). The gap between them is shrinkage.
Idempotent, coexists with create_all() — same pattern as every migration
since 015.
"""

from alembic import op
import sqlalchemy as sa

revision = "025_add_stock_counts"
down_revision = "024_add_enterprise_hierarchy"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _table_exists(name: str) -> bool:
    return name in _insp().get_table_names()


def upgrade():
    if not _table_exists("stock_counts"):
        op.create_table(
            "stock_counts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id"), nullable=False),
            sa.Column("inventory_item_id", sa.Integer(), sa.ForeignKey("inventory_items.id"), nullable=False),
            sa.Column("expected_quantity", sa.Float(), nullable=False),
            sa.Column("counted_quantity", sa.Float(), nullable=False),
            sa.Column("variance", sa.Float(), nullable=False),
            sa.Column("counted_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("notes", sa.String(), server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )
        op.create_index(
            "ix_stock_counts_restaurant_item", "stock_counts",
            ["restaurant_id", "inventory_item_id"],
        )
        op.create_index("ix_stock_counts_restaurant_id", "stock_counts", ["restaurant_id"])
        op.create_index("ix_stock_counts_inventory_item_id", "stock_counts", ["inventory_item_id"])


def downgrade():
    if _table_exists("stock_counts"):
        op.drop_table("stock_counts")
