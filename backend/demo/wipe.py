"""
backend/demo/wipe.py — remove the demo restaurants' business rows so they can be regenerated (docs/v2/SPEC.md S2.1).

DESTRUCTIVE, and scoped as tightly as it can be:
  * it only ever runs for the tenant named "Demo Restaurant" (`tenant_provisioning.DEMO_NAME`) — any other tenant
    raises before a single row is touched, however the caller got hold of it;
  * it only deletes rows that belong to that tenant's own restaurants (by `restaurant_id`, or by a parent that does);
  * it never deletes the tenant, the restaurants, the users, or the tables listed in `KEPT` (security and billing
    records, and LLM spend accounting).

`tests/test_demo_generator.py` asserts that every table with a `restaurant_id` column, and every table that hangs
off one, is listed here as either WIPED or KEPT with a reason — so a model added later cannot be silently forgotten
(left behind as stale rows, or deleted without anyone deciding it should be).
"""
from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

import models
from tenant_provisioning import DEMO_NAME


class WipeRefused(Exception):
    """Raised when asked to wipe something that is not the demo tenant."""


# (table name, how it is scoped). "direct" = has restaurant_id; otherwise (parent table, fk column on this table,
# parent's key) — children go first so no foreign key is ever violated.
_CHILDREN: list[tuple[str, str, str, str]] = [
    # table, fk column, parent table, parent's scoping route
    ("prep_times", "order_item_id", "order_items", "order_items<-orders"),
    ("order_items", "order_id", "orders", "direct"),
    ("stock_movements", "inventory_item_id", "inventory_items", "direct"),
    ("menu_ingredients", "menu_item_id", "menu_items", "direct"),
    ("workflow_steps", "run_id", "workflow_runs", "direct"),
    ("owner_os_messages", "conversation_id", "owner_os_conversations", "direct"),
]

# Tables with a `restaurant_id` column that ARE wiped (the demo's transactional data and everything derived from it),
# in an order that respects foreign keys (cash counts reference shifts; shifts reference staff).
WIPED: tuple[str, ...] = (
    "kitchen_incidents", "customer_feedback", "order_audits", "cash_drawer_counts", "labor_shifts", "staff_members",
    "stock_counts", "stock_transfers", "purchase_orders", "pricing_recommendations", "reservations", "tables",
    "agent_messages", "agent_executions", "agent_predictions", "memory_events", "conversation_turns", "customer_consents",
    "creative_takes", "attention_decisions", "owner_os_conversations", "owner_os_preferences", "workflow_runs",
    "restaurant_settings_audit", "restaurant_settings",
    # the money ledger (S3.1): expenses reference bills and categories, bills reference categories
    "licences", "expenses", "recurring_bills", "expense_categories",
    # the uploaded M-Pesa statements (S6.1): lines before the uploads that own them
    "mpesa_statement_lines", "mpesa_statement_uploads",
    # scheduled prices reference dishes, so they go before menu_items
    "scheduled_menu_prices", "operation_entries",
    # these two are parents of children above and are removed after them
    "orders", "inventory_items", "menu_items", "suppliers",
)

# Tables with a `restaurant_id` column that are deliberately NOT touched, each with the reason.
KEPT: dict[str, str] = {
    "agent_audit_log": "an audit log: never deleted by a re-seed (it records what the system did, including this run's inputs)",
    "impersonation_sessions": "security audit record of staff acting as the owner",
    "support_tickets": "support history is not demo data",
    "token_usage": "LLM spend accounting (billing record)",
}

# Child tables (no restaurant_id of their own) that follow their parent.
KEPT_CHILDREN: dict[str, str] = {
    "support_ticket_messages": "child of support_tickets, which is kept",
}


def _restaurant_ids(db: Session, tenant: models.Tenant) -> list[int]:
    return [r.id for r in db.query(models.Restaurant).filter(models.Restaurant.tenant_id == tenant.id).all()]


def assert_demo_tenant(tenant: models.Tenant | None) -> models.Tenant:
    if tenant is None or (tenant.name or "").strip().lower() != DEMO_NAME.lower():
        raise WipeRefused(
            f"refusing to wipe {getattr(tenant, 'name', None)!r}: only the tenant named {DEMO_NAME!r} may be re-seeded")
    return tenant


def wipe_demo(db: Session, tenant: models.Tenant, *, commit: bool = True) -> dict[str, int]:
    """Delete the demo restaurants' business rows. Returns {table: rows deleted}."""
    assert_demo_tenant(tenant)
    rids = _restaurant_ids(db, tenant)
    if not rids:
        return {}
    meta = models.Base.metadata.tables
    counts: dict[str, int] = {}

    def run(name: str, where) -> None:
        result = db.execute(delete(meta[name]).where(where))
        counts[name] = result.rowcount or 0

    # children first
    order_ids = select(meta["orders"].c.id).where(meta["orders"].c.restaurant_id.in_(rids))
    order_item_ids = select(meta["order_items"].c.id).where(meta["order_items"].c.order_id.in_(order_ids))
    run("prep_times", meta["prep_times"].c.order_item_id.in_(order_item_ids))
    run("order_items", meta["order_items"].c.order_id.in_(order_ids))
    for table, fk, parent, _route in _CHILDREN[2:]:
        parent_ids = select(meta[parent].c.id).where(meta[parent].c.restaurant_id.in_(rids))
        run(table, meta[table].c[fk].in_(parent_ids))

    for name in WIPED:
        run(name, meta[name].c.restaurant_id.in_(rids))
    if commit:
        db.commit()
    return {k: v for k, v in counts.items() if v}
