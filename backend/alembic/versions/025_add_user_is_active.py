"""add users.is_active for staff deactivation (tech-debt D18)

Revision ID: 025_add_user_is_active
Revises: 024_add_enterprise_hierarchy
Create Date: 2026-08-02 00:00:00.000000

Adds users.is_active (bool, default true). Previously there was no way to
deactivate a departing staff member's account short of changing their
password — get_current_user now rejects tokens/logins for is_active=False
users. Existing rows default to true, so nobody is locked out by this
migration.

Idempotent via inspector column checks, matching migration 020's pattern.
"""

from alembic import op
import sqlalchemy as sa

revision = "025_add_user_is_active"
down_revision = "024_add_enterprise_hierarchy"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    return any(c["name"] == column_name for c in sa.inspect(op.get_bind()).get_columns(table_name))


def upgrade():
    if not _column_exists("users", "is_active"):
        op.add_column("users", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade():
    if _column_exists("users", "is_active"):
        op.drop_column("users", "is_active")
