"""add missing FK indexes: staff_members.user_id, impersonation_sessions.tenant_id/restaurant_id

Revision ID: 036_add_missing_fk_indexes
Revises: 035_convert_inventory_cost_to_cents
Create Date: 2026-07-17 00:00:00.000000

Run with: alembic upgrade head

Fixes the two index gaps flagged in the 2026-07-17 database audit. Both are
FK columns queried directly (routers/staff.py filters staff_members by
user_id when resolving a login's roster link; impersonation_sessions is
tenant/restaurant-scoped on every lookup) but had no index — cheap query-plan
hygiene, low risk (index-only, no data change).

Idempotent via inspector checks, same posture as 033/034/035.
"""

from alembic import op
import sqlalchemy as sa

revision = "036_add_missing_fk_indexes"
down_revision = "035_convert_inventory_cost_to_cents"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _index_exists(table_name: str, index_name: str) -> bool:
    return any(ix["name"] == index_name for ix in _insp().get_indexes(table_name))


def upgrade():
    if not _index_exists("staff_members", "ix_staff_members_user_id"):
        op.create_index("ix_staff_members_user_id", "staff_members", ["user_id"])
    if not _index_exists("impersonation_sessions", "ix_impersonation_sessions_tenant_id"):
        op.create_index("ix_impersonation_sessions_tenant_id", "impersonation_sessions", ["tenant_id"])
    if not _index_exists("impersonation_sessions", "ix_impersonation_sessions_restaurant_id"):
        op.create_index("ix_impersonation_sessions_restaurant_id", "impersonation_sessions", ["restaurant_id"])


def downgrade():
    if _index_exists("impersonation_sessions", "ix_impersonation_sessions_restaurant_id"):
        op.drop_index("ix_impersonation_sessions_restaurant_id", table_name="impersonation_sessions")
    if _index_exists("impersonation_sessions", "ix_impersonation_sessions_tenant_id"):
        op.drop_index("ix_impersonation_sessions_tenant_id", table_name="impersonation_sessions")
    if _index_exists("staff_members", "ix_staff_members_user_id"):
        op.drop_index("ix_staff_members_user_id", table_name="staff_members")
