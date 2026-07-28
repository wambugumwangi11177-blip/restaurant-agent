"""add security_audit_log: audit trail for sensitive human actions

Revision ID: 025_add_security_audit_log
Revises: 024_add_enterprise_hierarchy
Create Date: 2026-07-28 00:00:00.000000

Run with: alembic upgrade head

Creates security_audit_log. Additive and idempotent — no existing table or
column is touched, so this is safe to run against a live database and coexists
with create_all().

Why a new table rather than extending agent_audit_log: that table records what
the AI did and requires a non-null restaurant_id and agent_name. The events this
one exists for cannot supply either — a failed login for an unknown email has no
user, no tenant and no restaurant, and that is exactly a row worth keeping.

Note on `target_ref`: it stores a keyed HMAC of the identifier, never the raw
value. The erasure endpoint writes here, and recording the raw phone number
would permanently retain the number the customer asked to have forgotten.
"""

from alembic import op
import sqlalchemy as sa

revision = "025_add_security_audit_log"
down_revision = "024_add_enterprise_hierarchy"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _table_exists(name: str) -> bool:
    return name in _insp().get_table_names()


def _index_names(table: str) -> set[str]:
    return {ix["name"] for ix in _insp().get_indexes(table)}


def upgrade():
    if not _table_exists("security_audit_log"):
        op.create_table(
            "security_audit_log",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("created_at", sa.DateTime(), nullable=False,
                      server_default=sa.func.now()),
            sa.Column("event_type", sa.String(), nullable=False),
            sa.Column("outcome", sa.String(), nullable=False, server_default="success"),
            # Nullable actor: a failed login against an unknown email has no user.
            sa.Column("actor_user_id", sa.Integer(),
                      sa.ForeignKey("users.id"), nullable=True),
            sa.Column("actor_email", sa.String(), nullable=True),
            sa.Column("tenant_id", sa.Integer(), nullable=True),
            sa.Column("restaurant_id", sa.Integer(), nullable=True),
            sa.Column("target_type", sa.String(), nullable=True),
            # HMAC of the identifier — never raw PII. See audit.hash_identifier().
            sa.Column("target_ref", sa.String(), nullable=True),
            sa.Column("source_ip", sa.String(), nullable=True),
            sa.Column("request_id", sa.String(), nullable=True),
            sa.Column("detail", sa.Text(), server_default="{}"),
        )

    existing = _index_names("security_audit_log")
    wanted = [
        ("ix_security_audit_log_created_at",     ["created_at"]),
        ("ix_security_audit_log_event_type",     ["event_type"]),
        ("ix_security_audit_log_actor_user_id",  ["actor_user_id"]),
        ("ix_security_audit_log_actor_email",    ["actor_email"]),
        ("ix_security_audit_log_tenant_id",      ["tenant_id"]),
        ("ix_security_audit_log_restaurant_id",  ["restaurant_id"]),
        ("ix_security_audit_log_request_id",     ["request_id"]),
        # Composite indexes for the two queries an investigator actually runs:
        # "what happened of this kind, recently" and "what did this actor do".
        ("ix_security_audit_event_created",      ["event_type", "created_at"]),
        ("ix_security_audit_actor_created",      ["actor_email", "created_at"]),
    ]
    for name, cols in wanted:
        if name not in existing:
            op.create_index(name, "security_audit_log", cols)


def downgrade():
    if _table_exists("security_audit_log"):
        op.drop_table("security_audit_log")
