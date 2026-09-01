"""add operational core tables (modifiers, till sessions, split payments, order columns, count sheets, waste, settings)

Revision ID: 030_add_operational_core_tables
Revises: 029_add_stock_movement_user_id
Create Date: 2026-08-24 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "030_add_operational_core_tables"
down_revision = "029_add_stock_movement_user_id"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    return any(c["name"] == column_name for c in sa.inspect(op.get_bind()).get_columns(table_name))


def upgrade():
    # 1. Order columns
    if not _column_exists("orders", "discount_cents"):
        with op.batch_alter_table("orders") as batch_op:
            batch_op.add_column(sa.Column("discount_cents", sa.Integer(), server_default="0", nullable=True))
            batch_op.add_column(sa.Column("discount_reason", sa.String(), server_default="", nullable=True))
            batch_op.add_column(sa.Column("void_reason", sa.String(), server_default="", nullable=True))
            batch_op.add_column(sa.Column("refund_cents", sa.Integer(), server_default="0", nullable=True))
            batch_op.add_column(sa.Column("refund_reason", sa.String(), server_default="", nullable=True))
            batch_op.add_column(sa.Column("tax_cents", sa.Integer(), server_default="0", nullable=True))
            batch_op.add_column(sa.Column("service_charge_cents", sa.Integer(), server_default="0", nullable=True))

    # 2. OrderItem columns
    if not _column_exists("order_items", "is_voided"):
        with op.batch_alter_table("order_items") as batch_op:
            batch_op.add_column(sa.Column("is_voided", sa.Boolean(), server_default="0", nullable=True))
            batch_op.add_column(sa.Column("void_reason", sa.String(), server_default="", nullable=True))
            batch_op.add_column(sa.Column("notes", sa.String(), server_default="", nullable=True))

    # 3. OrderPayments table
    if not _table_exists("order_payments"):
        op.create_table(
            "order_payments",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("payment_method", sa.String(), nullable=False),
            sa.Column("amount_cents", sa.Integer(), nullable=False),
            sa.Column("reference", sa.String(), server_default=""),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        )

    # 4. Modifiers tables
    if not _table_exists("modifier_groups"):
        op.create_table(
            "modifier_groups",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id"), nullable=False, index=True),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("min_selection", sa.Integer(), server_default="0"),
            sa.Column("max_selection", sa.Integer(), server_default="1"),
            sa.Column("is_required", sa.Boolean(), server_default="0"),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        )

    if not _table_exists("modifier_options"):
        op.create_table(
            "modifier_options",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("group_id", sa.Integer(), sa.ForeignKey("modifier_groups.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("price_delta_cents", sa.Integer(), server_default="0"),
            sa.Column("is_available", sa.Boolean(), server_default="1"),
        )

    if not _table_exists("menu_item_modifier_groups"):
        op.create_table(
            "menu_item_modifier_groups",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("menu_item_id", sa.Integer(), sa.ForeignKey("menu_items.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("modifier_group_id", sa.Integer(), sa.ForeignKey("modifier_groups.id", ondelete="CASCADE"), nullable=False, index=True),
        )

    if not _table_exists("order_item_modifiers"):
        op.create_table(
            "order_item_modifiers",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("order_item_id", sa.Integer(), sa.ForeignKey("order_items.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("modifier_option_id", sa.Integer(), sa.ForeignKey("modifier_options.id", ondelete="SET NULL"), nullable=True),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("price_delta_cents", sa.Integer(), server_default="0"),
        )

    # 5. Till Sessions
    if not _table_exists("till_sessions"):
        op.create_table(
            "till_sessions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id"), nullable=False, index=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("opening_float_cents", sa.Integer(), server_default="0"),
            sa.Column("closing_counted_cents", sa.Integer(), nullable=True),
            sa.Column("expected_cash_cents", sa.Integer(), nullable=True),
            sa.Column("variance_cents", sa.Integer(), nullable=True),
            sa.Column("variance_reason", sa.Text(), server_default=""),
            sa.Column("status", sa.String(), server_default="open"),
            sa.Column("opened_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("closed_at", sa.DateTime(), nullable=True),
            sa.Column("notes", sa.Text(), server_default=""),
        )

    # 6. Inventory Count sheets & lines
    if not _table_exists("inventory_counts"):
        op.create_table(
            "inventory_counts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id"), nullable=False, index=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("count_date", sa.Date(), nullable=False),
            sa.Column("status", sa.String(), server_default="draft"),
            sa.Column("notes", sa.Text(), server_default=""),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("posted_at", sa.DateTime(), nullable=True),
        )

    if not _table_exists("inventory_count_lines"):
        op.create_table(
            "inventory_count_lines",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("count_id", sa.Integer(), sa.ForeignKey("inventory_counts.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("inventory_item_id", sa.Integer(), sa.ForeignKey("inventory_items.id"), nullable=False, index=True),
            sa.Column("theoretical_qty", sa.Float(), server_default="0"),
            sa.Column("counted_qty", sa.Float(), server_default="0"),
            sa.Column("variance_qty", sa.Float(), server_default="0"),
        )

    # 7. Waste Log
    if not _table_exists("waste_logs"):
        op.create_table(
            "waste_logs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id"), nullable=False, index=True),
            sa.Column("inventory_item_id", sa.Integer(), sa.ForeignKey("inventory_items.id"), nullable=False, index=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("quantity", sa.Float(), nullable=False),
            sa.Column("unit", sa.String(), server_default=""),
            sa.Column("reason", sa.String(), nullable=False),
            sa.Column("cost_cents", sa.Integer(), server_default="0"),
            sa.Column("notes", sa.Text(), server_default=""),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        )

    # 8. Restaurant Settings
    if not _table_exists("restaurant_settings"):
        op.create_table(
            "restaurant_settings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id"), unique=True, nullable=False),
            sa.Column("tax_rate_percent", sa.Float(), server_default="16.0"),
            sa.Column("service_charge_percent", sa.Float(), server_default="0.0"),
            sa.Column("receipt_header", sa.String(), server_default=""),
            sa.Column("receipt_footer", sa.String(), server_default="Thank you for dining with us!"),
            sa.Column("currency", sa.String(), server_default="KES"),
            sa.Column("timezone", sa.String(), server_default="Africa/Nairobi"),
            sa.Column("opening_time", sa.String(), server_default="07:00"),
            sa.Column("closing_time", sa.String(), server_default="23:00"),
            sa.Column("lunch_start", sa.String(), server_default="11:30"),
            sa.Column("lunch_end", sa.String(), server_default="15:00"),
            sa.Column("dinner_start", sa.String(), server_default="18:00"),
            sa.Column("dinner_end", sa.String(), server_default="22:30"),
            sa.Column("stations_json", sa.Text(), server_default='["grill","fryer","salad","drinks","main","expo"]'),
            sa.Column("tenders_json", sa.Text(), server_default='["cash","mpesa","card"]'),
            sa.Column("kitchen_printer_url", sa.String(), server_default=""),
            sa.Column("receipt_printer_url", sa.String(), server_default=""),
        )


def downgrade():
    for table in [
        "restaurant_settings",
        "waste_logs",
        "inventory_count_lines",
        "inventory_counts",
        "till_sessions",
        "order_item_modifiers",
        "menu_item_modifier_groups",
        "modifier_options",
        "modifier_groups",
        "order_payments",
    ]:
        if _table_exists(table):
            op.drop_table(table)
