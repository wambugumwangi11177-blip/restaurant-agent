"""day cash close + close reminder time on restaurant."""
import sqlalchemy as sa
from alembic import op

revision = "j13_day_cash_close_reminders"
down_revision = "j12_restock_chain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()
    if "restaurants" in tables:
        cols = {c["name"] for c in inspector.get_columns("restaurants")}
        if "day_close_reminder_time" not in cols:
            op.add_column(
                "restaurants",
                sa.Column("day_close_reminder_time", sa.String(), nullable=False, server_default="22:00"),
            )
    if "day_cash_closes" not in tables:
        op.create_table(
            "day_cash_closes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id"), nullable=False),
            sa.Column("business_date", sa.Date(), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("cash_counted_cents", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("mpesa_counted_cents", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("expected_cash_cents", sa.Integer(), nullable=True),
            sa.Column("expected_mpesa_cents", sa.Integer(), nullable=True),
            sa.Column("expected_pending", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(), nullable=False, server_default="reported"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        )
        op.create_index("ix_day_cash_closes_restaurant_date", "day_cash_closes", ["restaurant_id", "business_date"])


def downgrade() -> None:
    op.drop_index("ix_day_cash_closes_restaurant_date", table_name="day_cash_closes")
    op.drop_table("day_cash_closes")
    op.drop_column("restaurants", "day_close_reminder_time")