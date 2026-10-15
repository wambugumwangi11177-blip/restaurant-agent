"""Money ledger: expense categories, expenses, recurring bills, licences.

docs/v2/SPEC.md §4 sprint S3.1. Additive only: four new tables, no change to existing ones.

Money is integer cents; an expense's day is a Nairobi calendar DATE. An expense is voided, never deleted, so
`expenses` keeps who/when/why columns; its foreign keys to users are SET NULL so removing a user never removes the ledger.

The backend Dockerfile runs create_all() before `alembic upgrade head`, so on a deploy the tables may already exist
with their indexes — same guard as 049-051. Offline (`--sql`) there is no connection to inspect, so the guard is skipped
and the real PostgreSQL DDL (up and down) is rendered for review.
"""
from alembic import op
import sqlalchemy as sa

revision = "052_money_ledger"
down_revision = "051_restaurant_settings"
branch_labels = None
depends_on = None


def _exists(name: str, *, offline: bool) -> bool:
    """Does the table exist? Offline (`--sql`) there is no connection to ask, so the caller says what to
    assume: upgrade assumes absent (render the CREATE), downgrade assumes present (render the DROP)."""
    if op.get_context().as_sql:
        return offline
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade():
    if not _exists("expense_categories", offline=False):
        op.create_table(
            "expense_categories",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("key", sa.String(length=40), nullable=False),
            sa.Column("name", sa.String(length=80), nullable=False),
            sa.Column("pnl_line", sa.String(length=16), nullable=False),
            sa.Column("is_fixed", sa.Boolean(), nullable=False),
            sa.Column("is_standard", sa.Boolean(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("restaurant_id", "key", name="uq_expense_categories_restaurant_key"),
        )
        op.create_index("ix_expense_categories_id", "expense_categories", ["id"])

    if not _exists("recurring_bills", offline=False):
        op.create_table(
            "recurring_bills",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("category_id", sa.Integer(), sa.ForeignKey("expense_categories.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("amount_cents", sa.Integer(), nullable=False),
            sa.Column("frequency", sa.String(length=8), nullable=False),
            sa.Column("due_day", sa.Integer(), nullable=False),
            sa.Column("due_month", sa.Integer(), nullable=True),
            sa.Column("start_on", sa.Date(), nullable=False),
            sa.Column("end_on", sa.Date(), nullable=True),
            sa.Column("supplier", sa.String(length=120), nullable=False),
            sa.Column("note", sa.String(length=500), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.CheckConstraint("amount_cents > 0", name="ck_recurring_bills_amount_pos"),
        )
        op.create_index("ix_recurring_bills_id", "recurring_bills", ["id"])
        op.create_index("ix_recurring_bills_restaurant", "recurring_bills", ["restaurant_id", "is_active"])

    if not _exists("expenses", offline=False):
        op.create_table(
            "expenses",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("category_id", sa.Integer(), sa.ForeignKey("expense_categories.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("amount_cents", sa.Integer(), nullable=False),
            sa.Column("paid_on", sa.Date(), nullable=False),
            sa.Column("method", sa.String(length=8), nullable=False),
            sa.Column("supplier", sa.String(length=120), nullable=False),
            sa.Column("note", sa.String(length=500), nullable=False),
            sa.Column("receipt_ref", sa.String(length=255), nullable=True),
            sa.Column("bill_id", sa.Integer(), sa.ForeignKey("recurring_bills.id", ondelete="SET NULL"), nullable=True),
            sa.Column("paid_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("updated_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("voided_at", sa.DateTime(), nullable=True),
            sa.Column("voided_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("void_reason", sa.String(length=200), nullable=True),
            sa.CheckConstraint("amount_cents > 0", name="ck_expenses_amount_pos"),
        )
        op.create_index("ix_expenses_id", "expenses", ["id"])
        op.create_index("ix_expenses_restaurant_paid_on", "expenses", ["restaurant_id", "paid_on"])
        op.create_index("ix_expenses_restaurant_category", "expenses", ["restaurant_id", "category_id"])

    if not _exists("licences", offline=False):
        op.create_table(
            "licences",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("issuer", sa.String(length=120), nullable=False),
            sa.Column("expires_on", sa.Date(), nullable=False),
            sa.Column("cost_cents", sa.Integer(), nullable=True),
            sa.Column("document_ref", sa.String(length=255), nullable=True),
            sa.Column("note", sa.String(length=500), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.CheckConstraint("cost_cents IS NULL OR cost_cents >= 0", name="ck_licences_cost_nonneg"),
        )
        op.create_index("ix_licences_id", "licences", ["id"])
        op.create_index("ix_licences_restaurant_expiry", "licences", ["restaurant_id", "expires_on"])


def downgrade():
    # children first: expenses -> recurring_bills -> expense_categories
    for table in ("licences", "expenses", "recurring_bills", "expense_categories"):
        if _exists(table, offline=True):
            op.drop_table(table)
