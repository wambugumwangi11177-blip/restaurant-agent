"""order audit trail, notification severity/escalation, supplier trust override

Revision ID: 038_order_audit_notif_severity_supplier_trust
Revises: 037_add_kitchen_incidents_and_gps_checkin
Create Date: 2026-07-21 00:00:00.000000

Run with: alembic upgrade head

Sprint 1 of the fraud-detection / escalation / tiered-PO-approval build:

  1. order_audits: previously nowhere to persist who voided/cancelled/refunded
     an order or changed its payment — only ever broadcast transiently on the
     event bus (actor_user_id in the payload), never written to a row. Fraud
     pattern detection (void spikes by staff, refund velocity) needs this to
     exist as queryable history. See models.py's OrderAudit docstring.
  2. notifications gains severity/acknowledged_at/escalation_level — the
     manager-escalation engine (ai/escalation/engine.py) scans for unacknowledged
     severe notifications and re-notifies on a timeout. Defaults keep every
     existing notify_users() call site a no-op for escalation (severity NULL).
  3. suppliers.requires_approval — nullable owner override for tiered PO
     auto-approval; NULL means "derive from reliability_score".

Idempotent via inspector checks, coexists with a create_all()-seeded schema.
"""

from alembic import op
import sqlalchemy as sa

revision = "038_order_audit_notif_severity_supplier_trust"
down_revision = "037_add_kitchen_incidents_and_gps_checkin"
branch_labels = None
depends_on = None

ORDER_AUDIT_ACTION_VALUES = ("void", "cancel", "refund", "payment_change")


def _insp():
    return sa.inspect(op.get_bind())


def _table_exists(name: str) -> bool:
    return name in _insp().get_table_names()


def _column_exists(table: str, column: str) -> bool:
    if not _table_exists(table):
        return False
    return column in [c["name"] for c in _insp().get_columns(table)]


def _index_exists(table: str, index_name: str) -> bool:
    if not _table_exists(table):
        return False
    return index_name in [i["name"] for i in _insp().get_indexes(table)]


def upgrade():
    if not _table_exists("order_audits"):
        # Create the enum type separately with checkfirst=True so that a
        # previously-failed migration that created the type but not the table
        # does not cause an error here.
        action_enum = sa.Enum(*ORDER_AUDIT_ACTION_VALUES, name="orderauditaction")
        action_enum.create(op.get_bind(), checkfirst=True)
        op.create_table(
            "order_audits",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
            sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id"), nullable=False),
            sa.Column("action", sa.Enum(*ORDER_AUDIT_ACTION_VALUES, name="orderauditaction", create_type=False), nullable=False),
            sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.func.now()),
        )
        op.create_index(
            "ix_order_audits_restaurant_actor_created", "order_audits",
            ["restaurant_id", "actor_user_id", "created_at"],
        )
        op.create_index("ix_order_audits_order", "order_audits", ["order_id"])

    if not _column_exists("notifications", "severity"):
        op.add_column("notifications", sa.Column("severity", sa.String(), nullable=True))
    if not _column_exists("notifications", "acknowledged_at"):
        op.add_column("notifications", sa.Column("acknowledged_at", sa.DateTime(), nullable=True))
    if not _column_exists("notifications", "escalation_level"):
        op.add_column("notifications", sa.Column(
            "escalation_level", sa.Integer(), nullable=False, server_default="0"))
    if not _index_exists("notifications", "ix_notifications_escalation_scan"):
        op.create_index(
            "ix_notifications_escalation_scan", "notifications", ["severity", "acknowledged_at"])

    if not _column_exists("suppliers", "requires_approval"):
        op.add_column("suppliers", sa.Column("requires_approval", sa.Boolean(), nullable=True))


def downgrade():
    if _column_exists("suppliers", "requires_approval"):
        op.drop_column("suppliers", "requires_approval")

    if _index_exists("notifications", "ix_notifications_escalation_scan"):
        op.drop_index("ix_notifications_escalation_scan", table_name="notifications")
    if _column_exists("notifications", "escalation_level"):
        op.drop_column("notifications", "escalation_level")
    if _column_exists("notifications", "acknowledged_at"):
        op.drop_column("notifications", "acknowledged_at")
    if _column_exists("notifications", "severity"):
        op.drop_column("notifications", "severity")

    if _table_exists("order_audits"):
        op.drop_table("order_audits")
        sa.Enum(name="orderauditaction").drop(op.get_bind(), checkfirst=True)