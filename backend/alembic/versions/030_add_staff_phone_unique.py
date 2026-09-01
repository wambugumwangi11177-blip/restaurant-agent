"""partial unique index on staff_members(restaurant_id, phone)

Revision ID: 030_add_staff_phone_unique
Revises: 029_add_mpesa_receipt_unique
Create Date: 2026-07-16 00:00:00.000000

Run with: alembic upgrade head

staff_members had no uniqueness on phone at all — two roster entries at the
same restaurant could share a phone number, which makes
routers/webhooks.py's inbound-message-to-staff-member resolution (by phone)
ambiguous. Partial unique index (WHERE phone IS NOT NULL, matching phone's
existing nullability — many roster entries have no phone at all).

DEPLOY SAFETY: guarded exactly like migrations 016/029 — count existing
duplicate (restaurant_id, phone) groups first and SKIP (log + leave
unenforced) rather than fail the deploy. No-op on SQLite (tests):
create_all() already carries the same partial index via models.py's
Index(..., sqlite_where=...).
"""

import logging

from alembic import op
import sqlalchemy as sa

revision = "030_add_staff_phone_unique"
down_revision = "029_add_mpesa_receipt_unique"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.030")

_INDEX_NAME = "uq_staff_members_restaurant_phone"


def _existing_index_names(inspector, table):
    return {ix["name"] for ix in inspector.get_indexes(table)}


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    inspector = sa.inspect(bind)
    if not inspector.has_table("staff_members"):
        return
    if _INDEX_NAME in _existing_index_names(inspector, "staff_members"):
        return

    dupes = bind.execute(sa.text(
        "SELECT COUNT(*) FROM (SELECT restaurant_id, phone FROM staff_members "
        "WHERE phone IS NOT NULL "
        "GROUP BY restaurant_id, phone HAVING COUNT(*) > 1) d"
    )).scalar()
    if dupes and dupes > 0:
        logger.warning(
            "[030] Skipping %s: %d duplicate (restaurant_id, phone) group(s) exist. "
            "Reconcile duplicates then re-run to enforce uniqueness.",
            _INDEX_NAME, dupes,
        )
        return

    op.execute(
        f'CREATE UNIQUE INDEX {_INDEX_NAME} ON staff_members (restaurant_id, phone) '
        f'WHERE phone IS NOT NULL'
    )


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    inspector = sa.inspect(bind)
    if inspector.has_table("staff_members") and _INDEX_NAME in _existing_index_names(inspector, "staff_members"):
        op.drop_index(_INDEX_NAME, table_name="staff_members")
