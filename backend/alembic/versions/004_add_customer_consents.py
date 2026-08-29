"""add customer_consents table

Revision ID: 004_add_customer_consents
Revises: 003_add_mpesa_fields_to_orders
Create Date: 2026-07-07 00:00:00.000000

Run with: alembic upgrade head

Minimal consent record for customer-facing PII collection (see models.py's
CustomerConsent docstring). Idempotent via inspector checks — see
001_add_agent_tables.py's docstring for why.
"""

from alembic import op
import sqlalchemy as sa

revision = "004_add_customer_consents"
down_revision = "003_add_mpesa_fields_to_orders"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _index_exists(table_name: str, index_name: str) -> bool:
    return any(idx["name"] == index_name for idx in sa.inspect(op.get_bind()).get_indexes(table_name))


def upgrade() -> None:
    if not _table_exists("customer_consents"):
        op.create_table(
            "customer_consents",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id"), nullable=False),
            sa.Column("customer_phone", sa.String(), nullable=False),
            sa.Column("purpose", sa.String(), nullable=False),
            sa.Column("consented_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _index_exists("customer_consents", "ix_customer_consents_id"):
        op.create_index("ix_customer_consents_id", "customer_consents", ["id"])
    if not _index_exists("customer_consents", "ix_customer_consents_restaurant_phone"):
        op.create_index(
            "ix_customer_consents_restaurant_phone",
            "customer_consents",
            ["restaurant_id", "customer_phone"],
        )


def downgrade() -> None:
    if _table_exists("customer_consents"):
        if _index_exists("customer_consents", "ix_customer_consents_restaurant_phone"):
            op.drop_index("ix_customer_consents_restaurant_phone", table_name="customer_consents")
        if _index_exists("customer_consents", "ix_customer_consents_id"):
            op.drop_index("ix_customer_consents_id", table_name="customer_consents")
        op.drop_table("customer_consents")