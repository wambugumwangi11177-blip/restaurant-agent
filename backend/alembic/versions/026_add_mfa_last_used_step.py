"""add users.mfa_last_used_step to make TOTP codes single-use

Revision ID: 026_add_mfa_last_used_step
Revises: 025_tenant_fk_and_owner_phone_integrity
Create Date: 2026-07-28 00:00:00.000000

Run with: alembic upgrade head

RFC 6238 §5.2 requires a TOTP code be accepted at most once. `verify_totp`
tolerates +/-1 30-second step for clock skew, which is correct — but with no
record of which step was already spent, a code captured by an attacker (shoulder
surf, phishing proxy, malware on the phone) stayed valid for the rest of that
~90-second window. This column stores the highest step each user has already
spent so a replay can be refused.

Nullable with no backfill: existing users simply have no spent step yet, so
their first post-deploy code is accepted normally and burned from then on.
BigInteger because the step is unix-seconds/30, which outgrows int32 in 2038.

Idempotent via an inspector column check (same idiom as migration 020, which
added the other two MFA columns), so it coexists with a create_all()-seeded
schema in tests and re-runs safely on any dialect.
"""

from alembic import op
import sqlalchemy as sa

revision = "026_add_mfa_last_used_step"
down_revision = "025_tenant_fk_and_owner_phone_integrity"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    return any(c["name"] == column_name for c in sa.inspect(op.get_bind()).get_columns(table_name))


def upgrade():
    if not _column_exists("users", "mfa_last_used_step"):
        op.add_column("users", sa.Column("mfa_last_used_step", sa.BigInteger(), nullable=True))


def downgrade():
    if _column_exists("users", "mfa_last_used_step"):
        op.drop_column("users", "mfa_last_used_step")
