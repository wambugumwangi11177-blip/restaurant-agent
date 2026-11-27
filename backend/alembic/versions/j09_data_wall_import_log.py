"""import_runs audit log; backfill inventory_items.restaurant_id for data wall.

Revision ID: j09_data_wall
Revises: j08_password_auth_at

Idempotent: backend-test (and any host that runs init_db before alembic
upgrade) already creates import_runs from the SQLAlchemy model, so a bare
create_table fails with DuplicateTable and the healthcheck never passes.
"""
import sqlalchemy as sa
from alembic import op

revision = "j09_data_wall"
down_revision = "j08_password_auth_at"
branch_labels = None
depends_on = None


def _tables():
    return set(sa.inspect(op.get_bind()).get_table_names())


def _indexes(table):
    if table not in _tables():
        return set()
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table)}


def upgrade() -> None:
    if "import_runs" not in _tables():
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
    if "ix_import_runs_restaurant_created" not in _indexes("import_runs"):
        op.create_index(
            "ix_import_runs_restaurant_created",
            "import_runs",
            ["restaurant_id", "created_at"],
        )

    op.execute(
        "UPDATE inventory_items SET restaurant_id = ("
        "SELECT id FROM restaurants ORDER BY id LIMIT 1"
        ") WHERE restaurant_id IS NULL AND EXISTS (SELECT 1 FROM restaurants)"
    )


def downgrade() -> None:
    if "ix_import_runs_restaurant_created" in _indexes("import_runs"):
        op.drop_index("ix_import_runs_restaurant_created", table_name="import_runs")
    if "import_runs" in _tables():
        op.drop_table("import_runs")
