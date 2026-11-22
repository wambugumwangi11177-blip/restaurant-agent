"""import_runs audit log; backfill inventory_items.restaurant_id for data wall.

Revision ID: j09_data_wall
Revises: j08_password_auth_at
"""
from alembic import op
import sqlalchemy as sa

revision = "j09_data_wall"
down_revision = "j08_password_auth_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "import_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("restaurant_id", sa.Integer(), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False, server_default=""),
        sa.Column("inserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("summary_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["restaurant_id"], ["restaurants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_import_runs_restaurant_created", "import_runs", ["restaurant_id", "created_at"])

    op.execute(
        "UPDATE inventory_items SET restaurant_id = ("
        "SELECT id FROM restaurants ORDER BY id LIMIT 1"
        ") WHERE restaurant_id IS NULL AND EXISTS (SELECT 1 FROM restaurants)"
    )


def downgrade() -> None:
    op.drop_index("ix_import_runs_restaurant_created", table_name="import_runs")
    op.drop_table("import_runs")