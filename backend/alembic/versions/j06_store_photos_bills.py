"""Zone day photos, bill due dates, and payment proof.

Revision ID: j06_store_photos_bills
Revises: j05_owner_review
"""
import sqlalchemy as sa
from alembic import op

revision = "j06_store_photos_bills"
down_revision = "j05_owner_review"
branch_labels = None
depends_on = None


def _tables():
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table):
    if table not in _tables():
        return set()
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade():
    bind = op.get_bind()
    if "store_zone_day_photos" not in _tables():
        op.create_table(
            "store_zone_day_photos",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id"), nullable=False, index=True),
            sa.Column("zone_id", sa.Integer(), sa.ForeignKey("stock_zones.id"), nullable=False, index=True),
            sa.Column("business_date", sa.Date(), nullable=False),
            sa.Column("phase", sa.String(), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("photo_storage_key", sa.String(), nullable=False),
            sa.Column("photo_content_type", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint(
                "restaurant_id", "zone_id", "business_date", "phase",
                name="uq_store_zone_day_photo",
            ),
        )
    if "store_zone_day_photo_checks" not in _tables():
        op.create_table(
            "store_zone_day_photo_checks",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("photo_id", sa.Integer(), sa.ForeignKey("store_zone_day_photos.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("status", sa.String(), nullable=False, server_default="pending"),
            sa.Column("model_name", sa.String(), nullable=True),
            sa.Column("result_json", sa.Text(), nullable=True),
            sa.Column("compared_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
    costs = _columns("running_costs")
    if costs:
        additions = [
            ("next_due_on", sa.Column("next_due_on", sa.Date(), nullable=True)),
            ("remind_days", sa.Column("remind_days", sa.Integer(), nullable=False, server_default="3")),
            ("payment_state", sa.Column("payment_state", sa.String(), nullable=False, server_default="none")),
            ("paid_at", sa.Column("paid_at", sa.DateTime(), nullable=True)),
            ("paid_by_user_id", sa.Column("paid_by_user_id", sa.Integer(), nullable=True)),
            ("mpesa_code", sa.Column("mpesa_code", sa.String(), nullable=True)),
            ("payment_receipt_storage_key", sa.Column("payment_receipt_storage_key", sa.String(), nullable=True)),
            ("payment_receipt_content_type", sa.Column("payment_receipt_content_type", sa.String(), nullable=True)),
        ]
        for name, column in additions:
            if name not in costs:
                op.add_column("running_costs", column)


def downgrade():
    raise RuntimeError("Zone day photos and bill due rows are kept.")