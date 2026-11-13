"""Owner review: bill answers, close confirmer, and the approval threshold.

Revision ID: j05_owner_review
Revises: j04_merge_store_pos
"""
import sqlalchemy as sa
from alembic import op

revision = "j05_owner_review"
down_revision = "j04_merge_store_pos"
branch_labels = None
depends_on = None


def _columns(table):
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade():
    restaurant = _columns("restaurants")
    if restaurant and "spoilage_approval_qty" not in restaurant:
        op.add_column(
            "restaurants",
            sa.Column("spoilage_approval_qty", sa.Float(), nullable=False, server_default="5"),
        )
    costs = _columns("running_costs")
    if costs:
        additions = [
            ("cadence", sa.Column("cadence", sa.String(), nullable=False, server_default="monthly")),
            ("due_day", sa.Column("due_day", sa.Integer(), nullable=True)),
            ("receipt_storage_key", sa.Column("receipt_storage_key", sa.String(), nullable=True)),
            ("receipt_content_type", sa.Column("receipt_content_type", sa.String(), nullable=True)),
            ("status", sa.Column("status", sa.String(), nullable=False, server_default="needs_approval")),
            ("delegated_to", sa.Column("delegated_to", sa.String(), nullable=True)),
            ("owner_note", sa.Column("owner_note", sa.Text(), nullable=False, server_default="")),
            ("approved_by_user_id", sa.Column("approved_by_user_id", sa.Integer(), nullable=True)),
            ("approved_at", sa.Column("approved_at", sa.DateTime(), nullable=True)),
        ]
        for name, column in additions:
            if name not in costs:
                op.add_column("running_costs", column)
    for table in ("spoilage_records", "day_closes"):
        columns = _columns(table)
        if columns and "owner_note" not in columns:
            op.add_column(table, sa.Column("owner_note", sa.Text(), nullable=False, server_default=""))
    closes = _columns("day_closes")
    if closes and "confirmer_user_id" not in closes:
        op.add_column("day_closes", sa.Column("confirmer_user_id", sa.Integer(), nullable=True))


def downgrade():
    raise RuntimeError("Owner review rows are kept.")
