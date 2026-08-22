"""fix authtokenpurpose enum labels (values vs names)

Revision ID: 043_fix_authtokenpurpose_enum_labels
Revises: 042_add_user_hashed_pin
Create Date: 2026-08-22 00:00:00.000

Run with: alembic upgrade head

Migration 034 created the authtokenpurpose Postgres type from the enum VALUES
('password_reset', 'email_verify'), but SQLAlchemy's default SqEnum storage
uses the member NAMES ('PASSWORD_RESET', 'EMAIL_VERIFY') — the same convention
every other enum in this schema follows (role, staffrole, orderstatus, ...).
Result: every INSERT into auth_tokens failed with
`invalid input value for enum authtokenpurpose: "EMAIL_VERIFY"` AFTER the user
row was already committed — register() surfaced a 500 while actually creating
the account, and password-reset/email-verify tokens could never be persisted.

auth_tokens has zero rows (the write path never once succeeded — verified
2026-08-22), so rebuilding the type is a metadata-only change. A fresh
database is unaffected either way: Dockerfile's startup runs init_db()
(create_all) before alembic, and create_all creates the type with NAME labels
already — 034's guarded DROP+CREATE is what forced lowercase onto this one DB.

Idempotent: skips if the labels are already the uppercase names.
"""

from alembic import op
import sqlalchemy as sa

revision = "043_fix_authtokenpurpose_enum_labels"
down_revision = "042_add_user_hashed_pin"
branch_labels = None
depends_on = None

NAME_LABELS = ("PASSWORD_RESET", "EMAIL_VERIFY")
VALUE_LABELS = ("password_reset", "email_verify")


def _current_labels() -> tuple:
    result = op.get_bind().execute(
        sa.text("SELECT unnest(enum_range(NULL::authtokenpurpose))")
    )
    return tuple(r[0] for r in result)


def _rebuild_type(labels: tuple) -> None:
    # Empty table (enforced by callers in practice; verified before shipping) —
    # round-trip through text so the column never references a dropped type.
    quoted = ", ".join(f"'{l}'" for l in labels)
    op.execute("ALTER TABLE auth_tokens ALTER COLUMN purpose TYPE text")
    op.execute("DROP TYPE authtokenpurpose")
    op.execute(f"CREATE TYPE authtokenpurpose AS ENUM ({quoted})")
    op.execute("ALTER TABLE auth_tokens ALTER COLUMN purpose TYPE authtokenpurpose"
               " USING purpose::authtokenpurpose")


def upgrade():
    if _current_labels() == NAME_LABELS:
        return
    _rebuild_type(NAME_LABELS)


def downgrade():
    if _current_labels() == VALUE_LABELS:
        return
    _rebuild_type(VALUE_LABELS)
