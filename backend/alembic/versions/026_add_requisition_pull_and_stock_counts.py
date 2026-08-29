"""kitchen requisition (pull) flow + physical stock counts (directive 017)

Revision ID: 026_add_requisition_pull_and_stock_counts
Revises: 025_add_staff_rbac_and_stock_custody
Create Date: 2026-07-15 12:00:00.000000

Run with: alembic upgrade head

Two changes, same release:

  1. stock_transfers gains a REQUESTED status (kitchen asks, no quantity
     committed yet) plus requested_by_user_id/requested_at. quantity and
     initiated_by_user_id — required (NOT NULL) since migration 025's
     store-initiated-only design — become nullable, since a REQUESTED row
     has neither until a stockkeeper fulfils it.
  2. New stock_counts table: physical counts, the independent check that
     keeps theft/shrinkage detection meaningful once ingredient deduction
     is automatic (see ai/stock_custody.py's StockCount docstring).

Idempotent via inspector checks, coexists with a create_all()-seeded schema.
"""

from alembic import op
import sqlalchemy as sa

revision = "026_add_requisition_pull_and_stock_counts"
down_revision = "025_add_staff_rbac_and_stock_custody"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _table_exists(name: str) -> bool:
    return name in _insp().get_table_names()


def _column_exists(table: str, column: str) -> bool:
    if not _table_exists(table):
        return False
    return column in [c["name"] for c in _insp().get_columns(table)]


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade():
    if _table_exists("stock_transfers"):
        # Native Postgres enum: adding a value to an existing type is its own
        # statement, separate from any column change, and must not be used in
        # the same transaction it's added in (fine here — nothing inserts a
        # REQUESTED row in this migration). SQLite has no native enum type
        # (sa.Enum falls back to a CHECK constraint there) and a fresh
        # create_all()-seeded test DB already has REQUESTED from models.py,
        # so this step is Postgres-only.
        if _is_postgres():
            op.execute("ALTER TYPE stocktransferstatus ADD VALUE IF NOT EXISTS 'REQUESTED'")
            op.execute("ALTER TABLE stock_transfers ALTER COLUMN quantity DROP NOT NULL")
            op.execute("ALTER TABLE stock_transfers ALTER COLUMN initiated_by_user_id DROP NOT NULL")

        if not _column_exists("stock_transfers", "requested_by_user_id"):
            op.add_column("stock_transfers", sa.Column(
                "requested_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True))
        if not _column_exists("stock_transfers", "requested_at"):
            op.add_column("stock_transfers", sa.Column("requested_at", sa.DateTime(), nullable=True))

    if not _table_exists("stock_counts"):
        op.create_table(
            "stock_counts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id"), nullable=False),
            sa.Column("inventory_item_id", sa.Integer(), sa.ForeignKey("inventory_items.id"), nullable=False),
            sa.Column("expected_quantity", sa.Float(), nullable=False),
            sa.Column("counted_quantity", sa.Float(), nullable=False),
            sa.Column("counted_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("counted_at", sa.DateTime(), nullable=True),
            sa.Column("notes", sa.Text(), server_default=sa.text("''"), nullable=True),
        )
        op.create_index("ix_stock_counts_restaurant_item", "stock_counts",
                         ["restaurant_id", "inventory_item_id"])


def downgrade():
    if _table_exists("stock_counts"):
        op.drop_table("stock_counts")

    if _table_exists("stock_transfers"):
        if _column_exists("stock_transfers", "requested_at"):
            op.drop_column("stock_transfers", "requested_at")
        if _column_exists("stock_transfers", "requested_by_user_id"):
            op.drop_column("stock_transfers", "requested_by_user_id")
        # Not reverting quantity/initiated_by_user_id to NOT NULL or removing
        # the REQUESTED enum value — Postgres can't drop an enum value at all,
        # and re-adding NOT NULL on a downgrade would fail on any row a
        # REQUESTED-flow left with a NULL quantity. Same posture as this
        # repo's other migrations: forward-safe, not bit-for-bit reversible.