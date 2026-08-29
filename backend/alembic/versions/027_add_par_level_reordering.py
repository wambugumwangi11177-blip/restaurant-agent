"""par-level reordering: inventory_items.par_level + default_supplier_id
(directive 018)

Revision ID: 027_add_par_level_reordering
Revises: 026_add_requisition_pull_and_stock_counts
Create Date: 2026-07-16 00:00:00.000000

Run with: alembic upgrade head

Two nullable columns on inventory_items:
  - par_level: the target quantity to restock up to. NULL means "not set" —
    an item with no par_level is simply never auto-drafted, never guessed at.
  - default_supplier_id: which supplier to draft a purchase order against.
    Also NULL-safe — no default supplier means no auto-draft for that item,
    same reasoning.

No changes to purchase_orders/suppliers — both tables and their columns
(including the free-string `status`) already existed and need nothing new
for this directive; only the CRUD/automation layer on top is new.

Idempotent via inspector checks, coexists with a create_all()-seeded schema.
"""

from alembic import op
import sqlalchemy as sa

revision = "027_add_par_level_reordering"
down_revision = "026_add_requisition_pull_and_stock_counts"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _column_exists(table: str, column: str) -> bool:
    if table not in _insp().get_table_names():
        return False
    return column in [c["name"] for c in _insp().get_columns(table)]


def upgrade():
    if not _column_exists("inventory_items", "par_level"):
        op.add_column("inventory_items", sa.Column("par_level", sa.Float(), nullable=True))
    if not _column_exists("inventory_items", "default_supplier_id"):
        op.add_column("inventory_items", sa.Column(
            "default_supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id"), nullable=True))


def downgrade():
    if _column_exists("inventory_items", "default_supplier_id"):
        op.drop_column("inventory_items", "default_supplier_id")
    if _column_exists("inventory_items", "par_level"):
        op.drop_column("inventory_items", "par_level")
