"""Finance: collect what is owed, and watch what each client costs to serve."""
from datetime import timedelta

import models
from ai.cost_model import cost_kes_cents
from time_utils import utcnow
from .. import kernel, tools  # noqa: F401

NAME = "finance"
REMIND_EVERY_DAYS = 7


def _overdue(sub, now) -> bool:
    if sub.status == "past_due":
        return True
    return (sub.plan != "free" and sub.status == "active"
            and sub.current_period_end is not None and sub.current_period_end < now)


def run(db, today=None):
    out, now = [], utcnow()
    for sub in db.query(models.Subscription).all():
        if not _overdue(sub, now):
            continue
        tenant = db.get(models.Tenant, sub.tenant_id)
        name = tenant.name if tenant else f"tenant {sub.tenant_id}"
        summary = f"Billing reminder: {name} ({sub.plan}) overdue"
        if kernel.already_proposed(db, "billing_reminder", summary, REMIND_EVERY_DAYS):
            continue
        out.append(kernel.propose(
            db, "finance.collections_agent", "billing_reminder",
            {"tenant_id": sub.tenant_id, "message": (
                f"Your {sub.plan} subscription for {name} is past due. Please renew in the "
                "billing page, or reply if something is wrong and we'll help.")}, summary))

    # Monthly unit-economics line (first week of the month), from recorded token use.
    today = today or now.date()
    if today.day <= 7:
        since = now - timedelta(days=30)
        cost_by_tenant: dict[str, int] = {}
        for r in db.query(models.TokenUsage).filter(models.TokenUsage.created_at >= since).all():
            rest = db.get(models.Restaurant, r.restaurant_id)
            key = rest.name if rest else str(r.restaurant_id)
            cost_by_tenant[key] = cost_by_tenant.get(key, 0) + cost_kes_cents(
                r.llm_model, r.input_tokens or 0, r.output_tokens or 0)
        total = sum(cost_by_tenant.values()) / 100
        top = ", ".join(f"{k} KES {v / 100:.0f}" for k, v in
                        sorted(cost_by_tenant.items(), key=lambda kv: -kv[1])[:3]) or "no usage"
        summary = f"Monthly LLM cost {today:%Y-%m}"
        if not kernel.already_proposed(db, "operator_alert", summary, 28):
            out.append(kernel.propose(
                db, "finance.unit_economics_agent", "operator_alert",
                {"title": f"LLM cost last 30 days: KES {total:.0f}", "body": f"Top: {top}. Estimate from list prices."},
                summary))
    return out
