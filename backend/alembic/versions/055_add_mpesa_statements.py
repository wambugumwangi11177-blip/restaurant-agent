"""M-Pesa statements: the files an owner uploaded and the transactions on them.

docs/v2/SPEC.md §4 sprint S6.1. Additive only: two new tables, no change to existing ones. Money is integer cents; times are naive UTC.
A receipt number is unique per restaurant, so the same payment uploaded twice is one row.

The backend Dockerfile runs create_all() before `alembic upgrade head`, so on a deploy the tables may already exist with their
indexes — same guard as 049-053. Offline (`--sql`) there is no connection to inspect, so the guard is skipped and the real
PostgreSQL DDL (up and down) is rendered for review.
"""
from alembic import op
import sqlalchemy as sa

revision = "055_mpesa_statements"
down_revision = "054_notification_push_held"
branch_labels = None
depends_on = None


def _exists(name: str, *, offline: bool) -> bool:
    """Does the table exist? Offline (`--sql`) there is no connection to ask, so the caller says what to
    assume: upgrade assumes absent (render the CREATE), downgrade assumes present (render the DROP)."""
    if op.get_context().as_sql:
        return offline
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade():
    if not _exists("mpesa_statement_uploads", offline=False):
        op.create_table(
            "mpesa_statement_uploads",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("filename", sa.String(length=255), nullable=False),
            sa.Column("parser", sa.String(length=32), nullable=False),
            sa.Column("uploaded_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("uploaded_at", sa.DateTime(), nullable=False),
            sa.Column("line_count", sa.Integer(), nullable=False),
            sa.Column("period_start", sa.DateTime(), nullable=True),
            sa.Column("period_end", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_mpesa_statement_uploads_id", "mpesa_statement_uploads", ["id"])
        op.create_index("ix_mpesa_uploads_restaurant_uploaded", "mpesa_statement_uploads", ["restaurant_id", "uploaded_at"])

    if not _exists("mpesa_statement_lines", offline=False):
        op.create_table(
            "mpesa_statement_lines",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("upload_id", sa.Integer(), sa.ForeignKey("mpesa_statement_uploads.id", ondelete="CASCADE"), nullable=False),
            sa.Column("receipt", sa.String(length=20), nullable=False),
            sa.Column("completed_at", sa.DateTime(), nullable=False),
            sa.Column("paid_in_cents", sa.Integer(), nullable=False),
            sa.Column("withdrawn_cents", sa.Integer(), nullable=False),
            sa.Column("details", sa.String(length=500), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("balance_cents", sa.Integer(), nullable=True),
            sa.UniqueConstraint("restaurant_id", "receipt", name="uq_mpesa_lines_restaurant_receipt"),
            sa.CheckConstraint("paid_in_cents >= 0 AND withdrawn_cents >= 0", name="ck_mpesa_lines_amounts"),
        )
        op.create_index("ix_mpesa_statement_lines_id", "mpesa_statement_lines", ["id"])
        op.create_index("ix_mpesa_lines_restaurant_completed", "mpesa_statement_lines", ["restaurant_id", "completed_at"])
        op.create_index("ix_mpesa_lines_upload", "mpesa_statement_lines", ["upload_id"])


def downgrade():
    if _exists("mpesa_statement_lines", offline=True):
        op.drop_table("mpesa_statement_lines")
    if _exists("mpesa_statement_uploads", offline=True):
        op.drop_table("mpesa_statement_uploads")
