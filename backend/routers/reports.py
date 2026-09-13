"""GET /api/v1/reports/{period} — deterministic drafted Restaurant OS reports.

period: daily | weekly | monthly | yearly. 422 for anything else.
"Drafted" = markdown template + real numbers interpolated. No LLM.
Shares _summarize() with the overview router (DRY).
"""
import re
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from database import get_db
from routers.overview import _restaurant_id, _summarize
from auth import require_staff_role
from time_utils import utcnow

router = APIRouter(prefix="/reports", tags=["reports"])

_PERIOD_SPANS = {
    "daily": timedelta(days=1),
    "weekly": timedelta(days=7),
    "monthly": timedelta(days=30),
    "yearly": timedelta(days=365),
}
_EAT_OFFSET = timedelta(hours=3)


def _range(period: str):
    now_eat = utcnow() + _EAT_OFFSET
    if period == "daily":
        start_eat = now_eat.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        start_eat = now_eat - _PERIOD_SPANS[period]
    return start_eat - _EAT_OFFSET, now_eat - _EAT_OFFSET


def _top_items(db: Session, rid: int, start, end, limit=5) -> list:
    rows = db.query(
        models.MenuItem.name,
        func.sum(models.OrderItem.quantity).label("qty"),
        func.sum(models.OrderItem.unit_price * models.OrderItem.quantity).label("sales"),
    ).join(models.Order, models.OrderItem.order_id == models.Order.id
    ).join(models.MenuItem, models.OrderItem.menu_item_id == models.MenuItem.id
    ).filter(
        models.Order.restaurant_id == rid,
        models.Order.created_at >= start, models.Order.created_at < end,
        models.Order.is_paid.is_(True),
        models.Order.status != models.OrderStatus.CANCELLED,
    ).group_by(models.MenuItem.name).order_by(func.sum(models.OrderItem.quantity).desc()).limit(limit).all()
    return [{"name": name, "qty": int(qty), "sales_kes": float(sales) / 100.0}
            for name, qty, sales in rows]


def _draft(period: str, range_label: str, core: dict, top: list) -> str:
    """Well-drafted report = good template + true numbers (deterministic)."""
    lines = [
        f"# {period.capitalize()} report — {range_label}",
        "",
        "## Overview",
        f"- Revenue: **KSh {core['revenue']:,.0f}**",
        f"- Orders: **{core['orders']}**",
        f"- Average order: **KSh {core['revenue'] / core['orders']:,.0f}**" if core["orders"] else "- No orders in this period.",
        "",
        "## Top selling items",
    ]
    if top:
        for t in top:
            lines.append(f"- {t['name']} — {t['qty']} sold (KSh {t['sales_kes']:,.0f})")
    else:
        lines.append("- No item-level sales recorded in this period.")
    lines += [
        "",
        "---",
        "Revenue includes paid, non-cancelled orders created in this period. This is not a payment cash-flow report.",
    ]
    return "\n".join(lines)


@router.get("/{period}")
def report(period: str, narrate: bool = True, db: Session = Depends(get_db), user=Depends(require_staff_role())):
    if period not in _PERIOD_SPANS:
        raise HTTPException(422, f"period must be one of {list(_PERIOD_SPANS)}")
    rid = _restaurant_id(db, user)
    start, end = _range(period)
    core = _summarize(db, rid, start, end)
    top = _top_items(db, rid, start, end)
    now_eat = utcnow() + _EAT_OFFSET
    if period == "daily":
        label = now_eat.strftime("%d %b %Y")
    elif period == "weekly":
        label = f"{(now_eat - timedelta(days=7)).strftime('%d %b')} – {now_eat.strftime('%d %b %Y')}"
    elif period == "monthly":
        label = f"{(now_eat - timedelta(days=30)).strftime('%d %b')} – {now_eat.strftime('%d %b %Y')}"
    else:
        label = f"{(now_eat - timedelta(days=365)).strftime('%d %b %Y')} – {now_eat.strftime('%d %b %Y')}"
    llm_text = _llm_narrative(period, label, core, top) if narrate else None
    return {
        "period": period,
        "range": label,
        "revenue": core["revenue"],
        "revenue_basis": "paid_non_cancelled_orders_by_creation_time",
        "orders": core["orders"],
        "top_items": top,
        "report_text": _draft(period, label, core, top),
        "llm_narrative": llm_text,
        "llm_used": llm_text is not None,
    }


# ─── LLM narrative (OpenRouter) ──────────────────────────────────────────────

def _llm_narrative(period: str, label: str, core: dict, top: list) -> str | None:
    """LLM-drafted narrative around DETERMINISTIC numbers. The prompt contains
    only real figures; the model is forbidden from inventing any. Returns None
    when no provider is configured or the call fails — the deterministic
    template remains the fallback, so a report is never blocked on the LLM."""
    from ai import llm_client
    if not llm_client.is_available():
        return None
    tops = "\n".join(f"- {t['name']}: {t['qty']} sold, {t['sales_kes']:.0f} KSh" for t in top) or "- none recorded"
    system = (
        "You draft business reports for a Kenyan restaurant owner. You are given "
        "REAL computed numbers — use exactly those figures, never invent or "
        "round differently. Write in clear, warm, direct English (the owner's "
        "tone). Structure: a 2-sentence overview, then 2-3 short bullet "
        "observations (what stands out), then one actionable recommendation. "
        "Keep it under 180 words. Currency is KSh. "
        "IMPORTANT: Output ONLY the finished report text. Do NOT write any "
        "planning, reasoning, meta-commentary or notes about the task — the "
        "first character of your answer is the first character of the report."
    )
    user = (
        f"Draft the {period} report ({label}).\n"
        f"Revenue: KSh {core['revenue']:,.0f}\n"
        f"Orders: {core['orders']}\n"
        + (f"Average order: KSh {core['revenue'] / core['orders']:,.0f}\n" if core["orders"] else "Average order: n/a (no orders)\n")
    )
    user += f"Top items:\n{tops}"
    try:
        text = llm_client.chat(
            [{"role": "user", "content": user}],
            system=system, max_tokens=500, tier="medium")
        return _grounded_reply(text, user)
    except Exception:  # noqa: BLE001 — LLM down never blocks a report
        return None


def _grounded_reply(text: str, evidence: str) -> str | None:
    """Keep deterministic output when an optional narrative invents figures."""
    from ai.reasoning.grounding import verify
    cleaned = _strip_reasoning_leak(text)
    checked = verify({"headline": cleaned}, evidence)
    return cleaned if cleaned and checked["verified"] else None


_LEAK_STARTERS = re.compile(
    r"^(we need|let me|i need|i'll|i will|to (produce|draft|write)|first|okay|sure|here's a plan|thinking|must have|should i|note:)",
    re.IGNORECASE,
)


def _strip_reasoning_leak(text: str) -> str:
    """nemotron-style reasoning models sometimes prepend their planning
    ('We need to produce a daily report...'). Strip any leading lines that
    are meta-commentary so the owner only sees the finished report. A line is
    meta if it starts with a leak-starter AND the following content restarts
    with a proper report line — simplest robust rule: drop leading lines that
    match leak starters or mention 'report for'/'numbers exactly' style task
    echo, until the first line that reads like report prose."""
    lines = (text or "").strip().splitlines()
    out: list[str] = []
    started = False
    for line in lines:
        stripped = line.strip()
        if not started and stripped and (
            _LEAK_STARTERS.match(stripped)
            or "report for" in stripped.lower()
            or "numbers exactly" in stripped.lower()
            or "we'll" in stripped.lower()
            or "we need to" in stripped.lower()
            or (stripped.endswith(":") and len(stripped) < 80)
        ):
            continue
        if stripped:
            started = True
        out.append(line)
    return "\n".join(out).strip() or text
