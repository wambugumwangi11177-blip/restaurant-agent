"""Storekeeper foundation: password gate, recipe yield, setup progress,
append-only staff entries, Eleven import keys, and private delivery evidence.

Revision ID: j01_storekeeper_foundation
Revises: 050_creative_takes
"""
from alembic import op
import sqlalchemy as sa

revision = "j01_storekeeper_foundation"
down_revision = "050_creative_takes"
branch_labels = None
depends_on = None


def _tables():
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table):
    if table not in _tables():
        return set()
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade():
    if "must_change_password" not in _columns("users"):
        op.add_column(
            "users",
            sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    ingredient_cols = _columns("menu_ingredients")
    if "yield_fraction" not in ingredient_cols:
        op.add_column(
            "menu_ingredients",
            sa.Column("yield_fraction", sa.Float(), nullable=False, server_default="1"),
        )
    if "recipe_unit" not in ingredient_cols:
        op.add_column("menu_ingredients", sa.Column("recipe_unit", sa.String(), nullable=True))
    if "created_by_user_id" not in ingredient_cols:
        op.add_column(
            "menu_ingredients",
            sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        )
    if "created_at" not in ingredient_cols:
        op.add_column("menu_ingredients", sa.Column("created_at", sa.DateTime(), nullable=True))

    if "staff_setup_progress" not in _tables():
        op.create_table(
            "staff_setup_progress",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id"), nullable=False),
            sa.Column("account_completed_at", sa.DateTime(), nullable=True),
            sa.Column("recipes_completed_at", sa.DateTime(), nullable=True),
            sa.Column("questionnaire_completed_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("user_id", name="uq_staff_setup_progress_user"),
        )
        op.create_index("ix_staff_setup_progress_id", "staff_setup_progress", ["id"])
        op.create_index("ix_staff_setup_progress_restaurant", "staff_setup_progress", ["restaurant_id"])

    if "staff_entry_audits" not in _tables():
        op.create_table(
            "staff_entry_audits",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("action", sa.String(), nullable=False),
            sa.Column("entity_type", sa.String(), nullable=False),
            sa.Column("entity_id", sa.Integer(), nullable=True),
            sa.Column("summary", sa.Text(), nullable=False),
            sa.Column("detail_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_staff_entry_audits_id", "staff_entry_audits", ["id"])
        op.create_index(
            "ix_staff_entry_audits_restaurant_created",
            "staff_entry_audits",
            ["restaurant_id", "created_at"],
        )

    if "import_applied_keys" not in _tables():
        op.create_table(
            "import_applied_keys",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("sheet", sa.String(), nullable=False),
            sa.Column("natural_key", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("restaurant_id", "sheet", "natural_key", name="uq_import_applied_key"),
        )
        op.create_index("ix_import_applied_keys_id", "import_applied_keys", ["id"])

    if "delivery_receipts" not in _tables():
        op.create_table(
            "delivery_receipts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id"), nullable=False),
            sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True),
            sa.Column("received_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("received_at", sa.DateTime(), nullable=False),
            sa.Column("notes", sa.Text(), nullable=False, server_default=""),
            sa.Column("status", sa.String(), nullable=False, server_default="draft"),
        )
        op.create_index("ix_delivery_receipts_id", "delivery_receipts", ["id"])
        op.create_index("ix_delivery_receipts_restaurant", "delivery_receipts", ["restaurant_id"])

    if "delivery_evidence_photos" not in _tables():
        op.create_table(
            "delivery_evidence_photos",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("receipt_id", sa.Integer(), sa.ForeignKey("delivery_receipts.id", ondelete="CASCADE"), nullable=False),
            sa.Column("kind", sa.String(), nullable=False),
            sa.Column("storage_key", sa.String(), nullable=False),
            sa.Column("content_type", sa.String(), nullable=False, server_default="image/jpeg"),
            sa.Column("byte_size", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("sha256", sa.String(), nullable=False, server_default=""),
            sa.Column("uploaded_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("uploaded_at", sa.DateTime(), nullable=False),
            sa.CheckConstraint("kind IN ('invoice', 'goods')", name="ck_delivery_photo_kind"),
        )
        op.create_index("ix_delivery_evidence_photos_id", "delivery_evidence_photos", ["id"])
        op.create_index("ix_delivery_evidence_photos_receipt", "delivery_evidence_photos", ["receipt_id"])

    if "delivery_receipt_lines" not in _tables():
        op.create_table(
            "delivery_receipt_lines",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("receipt_id", sa.Integer(), sa.ForeignKey("delivery_receipts.id", ondelete="CASCADE"), nullable=False),
            sa.Column("inventory_item_id", sa.Integer(), sa.ForeignKey("inventory_items.id", ondelete="SET NULL"), nullable=True),
            sa.Column("item_name", sa.String(), nullable=False),
            sa.Column("quantity", sa.Float(), nullable=False),
            sa.Column("unit", sa.String(), nullable=False, server_default=""),
            sa.Column("keyed_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("keyed_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_delivery_receipt_lines_id", "delivery_receipt_lines", ["id"])
        op.create_index("ix_delivery_receipt_lines_receipt", "delivery_receipt_lines", ["receipt_id"])

    if "delivery_vision_checks" not in _tables():
        op.create_table(
            "delivery_vision_checks",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("receipt_id", sa.Integer(), sa.ForeignKey("delivery_receipts.id", ondelete="CASCADE"), nullable=False),
            sa.Column("status", sa.String(), nullable=False, server_default="pending"),
            sa.Column("model_name", sa.String(), nullable=True),
            sa.Column("result_json", sa.Text(), nullable=True),
            sa.Column("compared_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_delivery_vision_checks_id", "delivery_vision_checks", ["id"])
        op.create_index("ix_delivery_vision_checks_receipt", "delivery_vision_checks", ["receipt_id"])


def downgrade():
    for table in (
        "delivery_vision_checks",
        "delivery_receipt_lines",
        "delivery_evidence_photos",
        "delivery_receipts",
        "import_applied_keys",
        "staff_entry_audits",
        "staff_setup_progress",
    ):
        if table in _tables():
            op.drop_table(table)
    for column in ("created_at", "created_by_user_id", "recipe_unit", "yield_fraction"):
        if column in _columns("menu_ingredients"):
            op.drop_column("menu_ingredients", column)
    if "must_change_password" in _columns("users"):
        op.drop_column("users", "must_change_password")
