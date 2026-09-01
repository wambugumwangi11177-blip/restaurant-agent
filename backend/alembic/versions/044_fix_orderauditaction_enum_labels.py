"""fix orderauditaction enum labels (values vs names)

Revision ID: 044_fix_orderauditaction_enum_labels
Revises: 043_fix_authtokenpurpose_enum_labels
Create Date: 2026-08-22 00:00:00.000

Run with: alembic upgrade head

Same class of bug as 034/043: migration 038 created the orderauditaction
Postgres type from the enum VALUES ('void', 'cancel', ...), but SQLAlchemy's
SqEnum storage writes the member NAMES ('VOID', 'CANCEL', ...). Every INSERT
into order_audits failed with `invalid input value for enum orderauditaction`
— so void/cancel/refund actions were never persisted, and the fraud-detection
scheduler job has crashed on every 2-hourly run (surfaced as
"[Fraud Check] Scheduler job failed" in the backend logs).

order_audits has zero rows (the write path never once succeeded — verified
2026-08-22), so rebuilding the type is metadata-only.

Full enum audit 2026-08-22 (all types, DB labels vs SQLAlchemy NAMEs):
authtokenpurpose OK (fixed by 043), deliverychannel OK, incidenttype OK,
orderauditaction MISMATCH (this migration), orderstatus OK, ordertype OK,
paymentmethod OK, reservationstatus OK, role OK, staffrole OK,
stockmovementtype OK, stocktransferstatus same labels in different order
(harmless — order only affects enum_range ordering, not validity),
supportticketstatus OK, tablestatus OK.

Idempotent: skips if the labels are already the uppercase names.
"""

from alembic import op
import sqlalchemy as sa

revision = "044_fix_orderauditaction_enum_labels"
down_revision = "043_fix_authtokenpurpose_enum_labels"
branch_labels = None
depends_on = None

NAME_LABELS = ("VOID", "CANCEL", "REFUND", "PAYMENT_CHANGE")
VALUE_LABELS = ("void", "cancel", "refund", "payment_change")


def _current_labels() -> tuple:
    result = op.get_bind().execute(
        sa.text("SELECT unnest(enum_range(NULL::orderauditaction))")
    )
    return tuple(r[0] for r in result)


def _rebuild_type(labels: tuple) -> None:
    # Empty table (the failed write path never persisted a row), so the
    # text round-trip below never has to map old values.
    quoted = ", ".join(f"'{l}'" for l in labels)
    op.execute("ALTER TABLE order_audits ALTER COLUMN action TYPE text")
    op.execute("DROP TYPE orderauditaction")
    op.execute(f"CREATE TYPE orderauditaction AS ENUM ({quoted})")
    op.execute("ALTER TABLE order_audits ALTER COLUMN action TYPE orderauditaction"
               " USING action::orderauditaction")


def upgrade():
    if _current_labels() == NAME_LABELS:
        return
    _rebuild_type(NAME_LABELS)


def downgrade():
    if _current_labels() == VALUE_LABELS:
        return
    _rebuild_type(VALUE_LABELS)
