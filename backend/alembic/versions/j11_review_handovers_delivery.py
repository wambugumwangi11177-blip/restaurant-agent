"""Owner review on handover/delivery discrepancies."""
import sqlalchemy as sa
from alembic import op

revision = "j11_review_handovers_delivery"
down_revision = "j10_team_schedule"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns(table)}


def upgrade():
    for table in ("kitchen_handovers", "delivery_receipts"):
        cols = _columns(table)
        if not cols:
            continue
        if "owner_review_status" not in cols:
            op.add_column(
                table,
                sa.Column("owner_review_status", sa.String(), nullable=False, server_default="none"),
            )
        if "owner_note" not in cols:
            op.add_column(table, sa.Column("owner_note", sa.Text(), nullable=False, server_default=""))
        if "reviewed_by_user_id" not in cols:
            op.add_column(table, sa.Column("reviewed_by_user_id", sa.Integer(), nullable=True))
        if "reviewed_at" not in cols:
            op.add_column(table, sa.Column("reviewed_at", sa.DateTime(), nullable=True))


def downgrade():
    raise RuntimeError("Owner review on handovers is kept.")