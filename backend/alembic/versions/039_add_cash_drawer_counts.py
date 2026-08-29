"""cash drawer counts (Sprint 4 — cash reconciliation)

Revision ID: 039_add_cash_drawer_counts
Revises: 038_order_audit_notif_severity_supplier_trust
Create Date: 2026-07-21 00:00:00.000000

Run with: alembic upgrade head

Scoped honestly: no bank-feed integration exists, so this is the buildable
half of "cash reconciliation" — a staff-entered physical drawer count
compared against Order rows for the same window (payment_method=CASH,
is_paid=True). See models.py's CashDrawerCount docstring and
ai/cash_reconciliation/intelligence.py.

Idempotent via inspector checks, coexists with a create_all()-seeded schema.
"""

from alembic import op
import sqlalchemy as sa

revision = "039_add_cash_drawer_counts"
down_revision = "038_order_audit_notif_severity_supplier_trust"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
 bind = op.get_bind()
 insp = sa.inspect(bind)
 return name in insp.get_table_names()


def upgrade():
 if not _table_exists("cash_drawer_counts"):
 op.create_table(
 "cash_drawer_counts",
 sa.Column("id", sa.Integer(), primary_key=True),
 sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id"), nullable=False),
 sa.Column("labor_shift_id", sa.Integer(),
 sa.ForeignKey("labor_shifts.id", ondelete="RESTRICT"), nullable=True),
 sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
 sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
 sa.Column("expected_amount_cents", sa.Integer(), nullable=False),
 sa.Column("counted_amount_cents", sa.Integer(), nullable=False),
 sa.Column("counted_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
 sa.Column("counted_at", sa.DateTime(timezone=True), nullable=True),
 sa.Column("notes", sa.Text(), nullable=True),
 )
 op.create_index(
 "ix_cash_drawer_counts_restaurant_window", "cash_drawer_counts",
 ["restaurant_id", "window_start"],
 )


def downgrade():
 if _table_exists("cash_drawer_counts"):
 op.drop_index("ix_cash_drawer_counts_restaurant_window", table_name="cash_drawer_counts")
 op.drop_table("cash_drawer_counts")