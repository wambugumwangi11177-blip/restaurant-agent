"""Chef PINs, kitchen handover, spoilage, and the end-of-day close.

Revision ID: j03_store_control
Revises: j02_store_intake
"""
from alembic import op
import sqlalchemy as sa

revision = "j03_store_control"
down_revision = "j02_store_intake"
branch_labels = None
depends_on = None


def _tables():
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade():
    if "store_chefs" not in _tables():
        op.create_table(
            "store_chefs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id"), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("photo_storage_key", sa.String(), nullable=True),
            sa.Column("photo_content_type", sa.String(), nullable=True),
            sa.Column("hashed_pin", sa.String(), nullable=False),
            sa.Column("failed_pin_attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("pin_locked_until", sa.DateTime(), nullable=True),
            sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_store_chefs_restaurant", "store_chefs", ["restaurant_id"])
    if "kitchen_handovers" not in _tables():
        op.create_table(
            "kitchen_handovers",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id"), nullable=False),
            sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("chef_id", sa.Integer(), sa.ForeignKey("store_chefs.id"), nullable=False),
            sa.Column("photo_storage_key", sa.String(), nullable=True),
            sa.Column("photo_content_type", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_kitchen_handovers_restaurant", "kitchen_handovers", ["restaurant_id"])
    if "kitchen_handover_lines" not in _tables():
        op.create_table(
            "kitchen_handover_lines",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("handover_id", sa.Integer(), sa.ForeignKey("kitchen_handovers.id", ondelete="CASCADE"), nullable=False),
            sa.Column("inventory_item_id", sa.Integer(), sa.ForeignKey("inventory_items.id"), nullable=False),
            sa.Column("item_name", sa.String(), nullable=False),
            sa.Column("quantity", sa.Float(), nullable=False),
            sa.Column("unit", sa.String(), nullable=False, server_default=""),
            sa.Column("from_zone", sa.String(), nullable=False, server_default="Main store"),
        )
        op.create_index("ix_kitchen_handover_lines_handover", "kitchen_handover_lines", ["handover_id"])
    if "handover_vision_checks" not in _tables():
        op.create_table(
            "handover_vision_checks",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("handover_id", sa.Integer(), sa.ForeignKey("kitchen_handovers.id", ondelete="CASCADE"), nullable=False),
            sa.Column("status", sa.String(), nullable=False, server_default="pending"),
            sa.Column("model_name", sa.String(), nullable=True),
            sa.Column("result_json", sa.Text(), nullable=True),
            sa.Column("compared_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_handover_vision_checks_handover", "handover_vision_checks", ["handover_id"])
    if "spoilage_records" not in _tables():
        op.create_table(
            "spoilage_records",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("chef_id", sa.Integer(), sa.ForeignKey("store_chefs.id"), nullable=False),
            sa.Column("inventory_item_id", sa.Integer(), sa.ForeignKey("inventory_items.id"), nullable=False),
            sa.Column("item_name", sa.String(), nullable=False),
            sa.Column("quantity", sa.Float(), nullable=False),
            sa.Column("unit", sa.String(), nullable=False, server_default=""),
            sa.Column("zone_name", sa.String(), nullable=False),
            sa.Column("reason_code", sa.String(), nullable=False),
            sa.Column("reason_text", sa.Text(), nullable=False, server_default=""),
            sa.Column("photo_storage_key", sa.String(), nullable=False),
            sa.Column("photo_content_type", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False, server_default="reported"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("approved_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("approved_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_spoilage_records_restaurant", "spoilage_records", ["restaurant_id"])
    if "day_closes" not in _tables():
        op.create_table(
            "day_closes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("chef_id", sa.Integer(), sa.ForeignKey("store_chefs.id"), nullable=True),
            sa.Column("working_alone", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("status", sa.String(), nullable=False, server_default="reported"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("approved_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("approved_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_day_closes_restaurant", "day_closes", ["restaurant_id"])
    if "day_close_lines" not in _tables():
        op.create_table(
            "day_close_lines",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("close_id", sa.Integer(), sa.ForeignKey("day_closes.id", ondelete="CASCADE"), nullable=False),
            sa.Column("inventory_item_id", sa.Integer(), sa.ForeignKey("inventory_items.id"), nullable=False),
            sa.Column("item_name", sa.String(), nullable=False),
            sa.Column("unit", sa.String(), nullable=False, server_default=""),
            sa.Column("expected_qty", sa.Float(), nullable=False),
            sa.Column("counted_qty", sa.Float(), nullable=False),
        )
        op.create_index("ix_day_close_lines_close", "day_close_lines", ["close_id"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION reject_staff_audit_change() RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'Staff entry audit rows are append-only';
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute("DROP TRIGGER IF EXISTS staff_entry_audits_no_update ON staff_entry_audits")
        op.execute("DROP TRIGGER IF EXISTS staff_entry_audits_no_delete ON staff_entry_audits")
        op.execute(
            "CREATE TRIGGER staff_entry_audits_no_update BEFORE UPDATE ON staff_entry_audits "
            "FOR EACH ROW EXECUTE FUNCTION reject_staff_audit_change()"
        )
        op.execute(
            "CREATE TRIGGER staff_entry_audits_no_delete BEFORE DELETE ON staff_entry_audits "
            "FOR EACH ROW EXECUTE FUNCTION reject_staff_audit_change()"
        )


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS staff_entry_audits_no_update ON staff_entry_audits")
        op.execute("DROP TRIGGER IF EXISTS staff_entry_audits_no_delete ON staff_entry_audits")
        op.execute("DROP FUNCTION IF EXISTS reject_staff_audit_change()")
    for name in (
        "day_close_lines",
        "day_closes",
        "spoilage_records",
        "handover_vision_checks",
        "kitchen_handover_lines",
        "kitchen_handovers",
        "store_chefs",
    ):
        if name in _tables():
            op.drop_table(name)
