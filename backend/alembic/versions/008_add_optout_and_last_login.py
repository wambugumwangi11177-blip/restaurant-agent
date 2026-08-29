"""add customer_optouts table and users.last_login_at

Revision ID: 008_add_optout_and_last_login
Revises: 007_add_login_lockout_fields
Create Date: 2026-07-07 00:00:00.000000

Run with: alembic upgrade head

Data-rights / compliance pass (2026-07-07): the platform sent winback/marketing
WhatsApp messages with no opt-out mechanism, contradicting the AUP's own
"provide a clear opt-out in every message and honour it" rule. This migration
adds the suppression list (customer_optouts) that the STOP handler writes and
the outbound send engine checks. It also adds users.last_login_at so the
staff-activity record the DPA describes actually exists. Idempotent via
inspector checks — see 001_add_agent_tables.py's docstring for why.
"""

from alembic import op
import sqlalchemy as sa

revision = "008_add_optout_and_last_login"
down_revision = "007_add_login_lockout_fields"
branch_labels = None
depends_on = None


def _get_bind():
    # op.get_bind() is deprecated in Alembic >= 1.7; use the migration context's
    # bind instead to avoid deprecation warnings.
    return op.get_context().bind


def _column_exists(table_name: str, column_name: str) -> bool:
    return any(c["name"] == column_name for c in sa.inspect(_get_bind()).get_columns(table_name))


def _table_exists(table_name: str) -> bool:
    return sa.inspect(_get_bind()).has_table(table_name)


def upgrade() -> None:
    if not _column_exists("users", "last_login_at"):
        op.add_column("users", sa.Column("last_login_at", sa.DateTime(), nullable=True))

    if not _table_exists("customer_optouts"):
        op.create_table(
            "customer_optouts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("customer_phone", sa.String(), nullable=False),
            sa.Column("source", sa.String(), server_default="whatsapp_stop"),
            sa.Column(
                "opted_out_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
        op.create_index("ix_customer_optouts_id", "customer_optouts", ["id"])
        op.create_index("ix_customer_optouts_customer_phone", "customer_optouts", ["customer_phone"], unique=True)


def downgrade() -> None:
    if _table_exists("customer_optouts"):
        op.drop_index("ix_customer_optouts_customer_phone", table_name="customer_optouts")
        op.drop_index("ix_customer_optouts_id", table_name="customer_optouts")
        op.drop_table("customer_optouts")
    if _column_exists("users", "last_login_at"):
        with op.batch_alter_table("users") as batch_op:
            batch_op.drop_column("last_login_at")