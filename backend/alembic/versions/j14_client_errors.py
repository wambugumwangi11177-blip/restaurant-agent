"""client_errors: screen problems reported from staff devices."""
import sqlalchemy as sa
from alembic import op

revision = "j14_client_errors"
down_revision = "j13_day_cash_close_reminders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "client_errors" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "client_errors",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("screen", sa.String(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_client_errors_id", "client_errors", ["id"])
    op.create_index("ix_client_errors_restaurant_created", "client_errors", ["restaurant_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_client_errors_restaurant_created", table_name="client_errors")
    op.drop_index("ix_client_errors_id", table_name="client_errors")
    op.drop_table("client_errors")
