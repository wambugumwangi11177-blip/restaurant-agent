"""add impersonation_sessions (real Owner "view as" sessions)

Revision ID: 033_add_impersonation_sessions
Revises: 032_add_support_tickets
Create Date: 2026-07-16 00:00:00.000000

Run with: alembic upgrade head

Backs the Owner-can-impersonate-a-staff-member feature: a row is the sole
source of truth for whether a live impersonation token is still valid, and
the audit-trail read surface (GET /staff/impersonation-log) for who
impersonated whom, when. Impersonation tokens embed the row's id as an
`imp_session_id` claim; auth.get_current_user checks this table on every
request rather than relying solely on JWT expiry, since "end this session
right now" can't be done by bumping the target's token_version (that would
also kill the target's own concurrent session).

Idempotent via inspector checks; coexists with create_all().
"""

from alembic import op
import sqlalchemy as sa

revision = "033_add_impersonation_sessions"
down_revision = "032_add_support_tickets"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _table_exists(name: str) -> bool:
    return name in _insp().get_table_names()


def upgrade():
    if not _table_exists("impersonation_sessions"):
        op.create_table(
            "impersonation_sessions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id"), nullable=False),
            sa.Column("impersonator_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("target_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("ended_at", sa.DateTime(), nullable=True),
            sa.Column("end_reason", sa.String(), nullable=True),
        )
        op.create_index("ix_impersonation_sessions_target", "impersonation_sessions", ["target_user_id"])
        op.create_index("ix_impersonation_sessions_impersonator", "impersonation_sessions", ["impersonator_user_id"])


def downgrade():
    if _table_exists("impersonation_sessions"):
        op.drop_table("impersonation_sessions")
