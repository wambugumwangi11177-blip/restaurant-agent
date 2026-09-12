"""GET /api/v1/ai/ask — route an owner question to the RIGHT intelligence
modules and return a sketch-format answer card.

Why this exists: /ai/strategy runs a fixed decision pipeline and returns the
same steps regardless of the question (verified 2026-09-12: "What will run
out soon?" and "How are my sales today?" both returned menu food-cost steps).
The owner's OS chat needs answers grounded in the module that owns the topic.

Routing map (all modules already existed in ai/ — this router just connects them):
  stock/reorder/waste/expire   -> ai/inventory_predictor + ai/reorder
  sales/revenue/sell           -> ai/revenue_forecaster + ops_manager quick stats
  bookings/no-show/reservation -> ai/reservation_optimizer
  kitchen/prep/station         -> ai/kds_intelligence
  staff/labor/shift            -> ai/labor/intelligence
  menu/popular/remove          -> ai/menu_engineer
  price/pricing/margin         -> ai/pricing.recommendations
  profit/losing money          -> ai/profit/intelligence
  anything else                -> ai/ops_manager dashboard summary
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

import models
from database import get_db
from auth import require_staff_role
from routers.reports import _strip_reasoning_leak

router = APIRouter(prefix="/ai", tags=["ai"])

try:  # limiter is optional here; the route is DB-bound but cheap
    from rate_limit import limiter
except Exception:  # pragma: no cover
    limiter = None


class AnswerCard(BaseModel):
    finding: str
    why: str
    impact: str
    recommendation: str
    module: str
    steps: list[dict]
    data: dict = {}


def _money(cents: float | None) -> str:
    return f"KSh {(cents or 0) / 100:,.0f}"


def _route(question: str) -> str:
    q = question.lower()
    rules: list[tuple[str, tuple[str, ...]]] = [
        ("stock", ("run out", "stock", "waste", "wast", "reorder", "expire", "inventory", "low stock", "shortage", "out of")),
        ("bookings", ("book", "reservation", "no-show", "no show", "covers", "table", "waitlist")),
        ("kitchen", ("kitchen", "prep", "station", "backed up", "bottleneck", "delay", "ticket")),
        ("staff", ("staff", "labor", "shift", "understaff", "overstaff", "schedule", "overtime", "productivity")),
        ("pricing", ("price", "pricing", "margin", "increase", "underpriced", "overpriced")),
        ("menu", ("menu", "popular", "remove", "promote", "best-sell", "best sell", "dish", "item")),
        ("profit", ("profit", "losing money", "money losing", "cost", "expense", "leak")),
        ("revenue", ("sale", "revenue", "sell", "income", "today", "forecast", "trending", "slow")),
    ]
    for module, keywords in rules:
        if any(k in q for k in keywords):
            return module
    return "ops"


def _answer_stock(db: Session, rid: int, q: str) -> dict:
    from ai.inventory_predictor import get_inventory_predictions
    preds = get_inventory_predictions(db, rid)
    items = preds.get("predictions") or preds.get("items") or []
    soon = [p for p in items if (p.get("days_until_stockout") is not None and p["days_until_stockout"] <= 7)]
    low = [p for p in items if p.get("status") in ("low", "critical") or p.get("is_low")]
    focus = soon or low
    if focus:
        names = ", ".join(p.get("item_name") or p.get("name", "?") for p in focus[:3])
        finding = (f"{len(focus)} item(s) projected to run out within a week: {names}."
                   if soon else f"{len(low)} item(s) below reorder point: {names}.")
        why = "Based on your last 14 days of usage velocity versus current quantity on hand."
        impact = "Avoids emergency buying at higher prices and mid-service menu gaps"
        rec = f"Raise today's order for {focus[0].get('item_name') or focus[0].get('name', 'the affected items')} and confirm the next delivery slot."
        steps = [
            {"action": f"Reorder {p.get('item_name') or p.get('name')}", "why": f"{p.get('days_until_stockout', '?')} days of stock left at current usage"}
            for p in focus[:4]
        ]
    else:
        finding = "Nothing is projected to run out in the next 7 days."
        why = "All tracked items have enough cover at current usage rates."
        impact = "—"
        rec = "No reorder needed today. Re-check after tomorrow's service."
        steps = []
    return {"finding": finding, "why": why, "impact": impact, "recommendation": rec,
            "module": "reorder", "steps": steps, "data": {"candidates": len(focus)}}


def _answer_revenue(db: Session, rid: int, q: str) -> dict:
    from ai.revenue_forecaster import get_revenue_forecast
    from routers.overview import _summarize, _eat_range  # EAT-day truth
    start, end = _eat_range("today")
    core = _summarize(db, rid, start, end)
    try:
        fc = get_revenue_forecast(db, rid)
        forecast = fc.get("forecast") or fc.get("predictions") or {}
        trend_txt = fc.get("trend") or fc.get("summary") or ""
    except Exception:
        forecast, trend_txt = {}, ""
    finding = f"Revenue today is {_money(core['revenue'] * 100)} across {core['orders']} orders."
    why = "Live from your order data for the Nairobi calendar day so far."
    # core["revenue"] is already KES (overview's _summarize converts cents→KES);
    # avg_order must stay in KES — multiplying by 100 again showed absurd figures
    # (verified in browser 2026-09-12: "KSh 199,467" instead of KSh 1,995).
    impact = f"Average order {_money(core['revenue'] * 100 / core['orders'])} per order" if core["orders"] else "Average order — no orders yet today"
    rec = trend_txt if isinstance(trend_txt, str) and trend_txt else "Compare against the 7-day trend on Home to see if today is ahead or behind."
    steps = []
    if isinstance(forecast, dict):
        for k, v in list(forecast.items())[:3]:
            steps.append({"action": f"{k}: {v}" if not isinstance(v, (int, float)) else f"{k}: {v}"})
    return {"finding": finding, "why": why, "impact": impact, "recommendation": rec,
            "module": "revenue", "steps": steps, "data": {"today": core}}


def _answer_bookings(db: Session, rid: int, q: str) -> dict:
    from ai.reservation_optimizer import get_reservation_insights
    ins = get_reservation_insights(db, rid)
    no_show = ins.get("no_show") or ins.get("no_show_rate") or {}
    covers = ins.get("today") or ins.get("covers_today") or {}
    rate = no_show.get("rate") if isinstance(no_show, dict) else no_show
    lost = no_show.get("lost_revenue") if isinstance(no_show, dict) else None
    finding = f"No-show rate is {rate if rate is not None else 'n/a'}{' · ' + _money(lost) + ' lost to no-shows' if lost else ''}."
    recs = ins.get("recommendations") or []
    why = "Computed from your reservation history: completion rate, lead time and party size patterns."
    impact = _money(lost) if lost else "Protects table availability"
    rec = (recs[0] if isinstance(recs[0], str) else recs[0].get("action", "Enable deposit requests for peak slots")) if recs else "Enable deposit requests for peak slots."
    steps = [{"action": r if isinstance(r, str) else r.get("action", ""), "why": r.get("why", "") if isinstance(r, dict) else ""}
             for r in recs[:4] if (isinstance(r, str) or r.get("action"))]
    return {"finding": finding, "why": why, "impact": impact, "recommendation": rec,
            "module": "reservations", "steps": steps, "data": {}}


def _answer_kitchen(db: Session, rid: int, q: str) -> dict:
    from ai.kds_intelligence import get_kds_intelligence
    kds = get_kds_intelligence(db, rid)
    bottlenecks = kds.get("bottlenecks") or []
    stations = kds.get("stations") or []
    if bottlenecks:
        b0 = bottlenecks[0]
        name = b0.get("station") or b0.get("name") or "a station"
        finding = f"{name} is the current bottleneck: {b0.get('detail', b0.get('reason', 'queue above target'))}."
    elif stations:
        slowest = max(stations, key=lambda s: s.get("avg_minutes", 0) if isinstance(s.get("avg_minutes"), (int, float)) else 0)
        finding = f"Slowest station: {slowest.get('station') or slowest.get('name')} at {slowest.get('avg_minutes')} min average."
    else:
        finding = "No bottlenecks detected right now — the kitchen is on pace."
    why = "From live kitchen display data: prep times per item and queue depth per station."
    impact = "Protects ticket times during rush"
    recs = kds.get("recommendations") or []
    rec = (recs[0] if isinstance(recs[0], str) else recs[0].get("action", "")) if recs else "Keep the current line setup."
    steps = [{"action": r if isinstance(r, str) else r.get("action", "")} for r in recs[:4]]
    return {"finding": finding, "why": why, "impact": impact, "recommendation": rec,
            "module": "kitchen", "steps": steps, "data": {}}


def _answer_staff(db: Session, rid: int, q: str) -> dict:
    from ai.labor.intelligence import get_labor_intelligence
    labor = get_labor_intelligence(db, rid)
    pct = labor.get("labor_cost_pct") or labor.get("cost_pct")
    recs = labor.get("recommendations") or []
    finding = f"Labor cost is {pct}% of revenue." if pct is not None else "Labor intelligence loaded."
    if pct is not None:
        finding += " " + ("Within the 25-35% healthy range." if 25 <= float(pct) <= 35 else "Outside the 25-35% healthy band — review shift lengths.")
    why = "From clocked shifts versus revenue over the current period."
    impact = "Labor is typically your largest controllable cost"
    rec = (recs[0] if isinstance(recs[0], str) else recs[0].get("action", "")) if recs else "Align the biggest shifts with your peak windows."
    steps = [{"action": r if isinstance(r, str) else r.get("action", "")} for r in recs[:4]]
    return {"finding": finding, "why": why, "impact": impact, "recommendation": rec,
            "module": "labor", "steps": steps, "data": {}}


def _answer_menu(db: Session, rid: int, q: str) -> dict:
    from ai.menu_engineer import get_menu_engineering
    me = get_menu_engineering(db, rid)
    summary = me.get("summary") or {}
    stars = me.get("stars") or summary.get("stars") or []
    dogs = me.get("dogs") or summary.get("dogs") or []
    parts = []
    if stars:
        parts.append(f"{len(stars)} star item(s) driving profit")
    if dogs:
        parts.append(f"{len(dogs)} dog item(s) dragging the menu")
    finding = "Menu mix: " + (" · ".join(parts) if parts else "no clear stars or dogs yet — needs more order history.")
    why = "Menu engineering classifies items by popularity vs margin (Star/Plowhorse/Puzzle/Dog)."
    impact = f"Avg food cost {summary.get('avg_food_cost_pct', '—')}" if summary else "—"
    rec = f"Promote {stars[0] if stars else 'your margin leaders'}; {('review or rework ' + dogs[0]) if dogs else 'keep testing puzzles'}." if (stars or dogs) else "Keep collecting order data for classification."
    steps = [{"action": f"Promote: {s}" if isinstance(s, str) else s.get("name", "")} for s in stars[:3]]
    steps += [{"action": f"Review/rework: {d}" if isinstance(d, str) else d.get("name", "")} for d in dogs[:2]]
    return {"finding": finding, "why": why, "impact": impact, "recommendation": rec,
            "module": "menu", "steps": steps, "data": {}}


def _answer_pricing(db: Session, rid: int, q: str) -> dict:
    from ai.pricing.recommendations import get_pricing_intelligence
    pi = get_pricing_intelligence(db, rid)
    recs = pi.get("recommendations") or pi.get("items") or []
    if recs:
        r0 = recs[0]
        finding = f"{len(recs)} pricing recommendation(s) open. Top: {r0.get('item') or r0.get('name', '?')} — {r0.get('suggestion', r0.get('reason', ''))}."
    else:
        finding = "No pricing changes recommended right now."
    why = "Item margins versus your target band and recent cost movements."
    impact = (r0.get("expected_impact") if recs and isinstance(recs[0], dict) else None) or "Restores margin floor"
    rec = "Open the pricing recommendation and approve the change to apply it."
    steps = [{"action": (r.get("item", "") + ": " + r.get("suggestion", "")) if isinstance(r, dict) else str(r)} for r in recs[:4]]
    return {"finding": finding, "why": why, "impact": impact, "recommendation": rec,
            "module": "pricing", "steps": steps, "data": {}}


def _answer_profit(db: Session, rid: int, q: str) -> dict:
    from ai.profit.intelligence import get_profit_intelligence
    pi = get_profit_intelligence(db, rid)
    leaks = pi.get("leaks") or pi.get("issues") or []
    total = pi.get("total_leak") or pi.get("monthly_impact")
    if leaks:
        l0 = leaks[0]
        finding = f"Biggest leak: {l0.get('area') or l0.get('name', '?')} — {l0.get('detail', '')}"
    else:
        finding = "No significant profit leaks detected this period."
    why = "Cross-references food cost, waste, discounts and labor against revenue."
    impact = _money(total) if total else "—"
    recs = pi.get("recommendations") or []
    rec = (recs[0] if isinstance(recs[0], str) else recs[0].get("action", "")) if recs else "Maintain current cost controls."
    steps = [{"action": r if isinstance(r, str) else r.get("action", ""), "why": (r.get("why", "") if isinstance(r, dict) else "")} for r in leaks[:4] or recs[:4]]
    return {"finding": finding, "why": why, "impact": impact, "recommendation": rec,
            "module": "profit", "steps": steps, "data": {}}


def _answer_ops(db: Session, rid: int, q: str) -> dict:
    from ai.ops_manager import get_operations_dashboard
    d = get_operations_dashboard(db, rid)
    hb = d.get("health_breakdown") or []
    worst = min(hb, key=lambda b: b.get("score", 100)) if hb else None
    qs = d.get("quick_stats") or {}
    if worst:
        finding = f"Health score {d.get('health_score', '—')}/100. Weakest area: {worst['category']} ({worst['score']}) — {worst.get('detail', '')}"
    else:
        finding = f"Today: {qs.get('today_orders', 0)} orders, {_money(qs.get('today_revenue', 0))} revenue."
    why = "Overall operations health across menu, revenue trend, kitchen, inventory and reservations."
    impact = f"Day-over-day: {qs.get('day_over_day_change', 0):+.1f}%" if qs else "—"
    rec = (d.get("opportunities") or [{}])[0].get("opportunity", "Review the attention cards on Home.")
    steps = [{"action": o.get("opportunity", ""), "why": o.get("detail", "")} for o in (d.get("opportunities") or [])[:4]]
    return {"finding": finding, "why": why, "impact": impact, "recommendation": rec,
            "module": "ops", "steps": steps, "data": {}}


_HANDLERS = {
    "stock": _answer_stock,
    "revenue": _answer_revenue,
    "bookings": _answer_bookings,
    "kitchen": _answer_kitchen,
    "staff": _answer_staff,
    "menu": _answer_menu,
    "pricing": _answer_pricing,
    "profit": _answer_profit,
    "ops": _answer_ops,
}


@router.get("/ask", response_model=AnswerCard)
def ask(
    question: str = Query(..., min_length=3, max_length=500),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_staff_role()),
):
    rid = user.active_restaurant_id
    if rid is None:
        row = db.query(models.Restaurant.id).filter(models.Restaurant.tenant_id == user.tenant_id).first()
        rid = row[0] if row else 0
        if not rid:
            raise HTTPException(404, "No restaurant found for this account")
    module = _route(question)
    try:
        card = _HANDLERS[module](db, rid, question)
    except Exception as exc:  # module failure must not 500 the chat — degrade to ops
        card = _answer_ops(db, rid, question)
        card["steps"] = card.get("steps", [])
        card["data"] = {"fallback_reason": str(exc)[:120]}
    return card


# ─── LLM chat (real-time, OpenRouter) ────────────────────────────────────────

class ChatBody(BaseModel):
    question: str
    history: list[dict] = []  # [{"role","content"}] prior turns, optional


@router.post("/chat")
def chat_llm(body: ChatBody, db: Session = Depends(get_db),
             user: models.User = Depends(require_staff_role())):
    """Real-time conversational answer: routes the question to the right ai/
    module for GROUNDED DATA, then lets the LLM (OpenRouter) write a
    conversational reply from that data. The LLM never invents numbers — its
    prompt contains only the module's real figures, and the raw data ships
    alongside so the client can show both."""
    rid = user.active_restaurant_id
    if rid is None:
        row = db.query(models.Restaurant.id).filter(
            models.Restaurant.tenant_id == user.tenant_id).first()
        rid = row[0] if row else 0
        if not rid:
            raise HTTPException(404, "No restaurant found for this account")

    module = _route(body.question)
    try:
        card = _HANDLERS[module](db, rid, body.question)
    except Exception as exc:  # noqa: BLE001 — grounding failure falls back to ops
        card = _answer_ops(db, rid, body.question)
        card["data"] = {"fallback_reason": str(exc)[:120]}

    from ai import llm_client
    llm_reply = None
    if llm_client.is_available():
        restaurant_name = db.query(models.Restaurant.name).filter(
            models.Restaurant.id == rid).scalar() or "your restaurant"
        context = (
            f"Restaurant: {restaurant_name} (Nairobi, Kenya).\n"
            f"Topic module: {module}\n"
            f"Grounded data from our systems (REAL numbers — never contradict, "
            f"never invent figures):\n"
            f"- Finding: {card['finding']}\n"
            f"- Why: {card['why']}\n"
            f"- Impact: {card['impact']}\n"
            f"- Recommended action: {card['recommendation']}\n"
            f"- Steps: {[(s.get('action'), s.get('why', '')) for s in card.get('steps', [])]}\n"
            f"- Extra data: {card.get('data', {})}\n"
        )
        system = (
            "You are the Restaurant OS assistant for a Kenyan restaurant owner. "
            "Answer in the same language the owner uses. Be warm, direct and "
            "practical — like a sharp operations partner, not a corporate report. "
            "Use ONLY the grounded data provided; never invent numbers. Money is "
            "KSh. Keep answers under 120 words unless the owner asks for detail. "
            "End with one concrete next action when relevant.\n\n" + context
        )
        messages = (body.history or [])[-6:] + [
            {"role": "user", "content": body.question}]
        try:
            llm_reply = llm_client.chat(
                messages, system=system, max_tokens=400, tier="medium")
            llm_reply = _strip_reasoning_leak(llm_reply)
        except Exception as exc:  # noqa: BLE001 — LLM down ≠ chat down
            llm_reply = None
            card["data"]["llm_error"] = str(exc)[:120]

    return {
        "module": module,
        "grounded": card,
        "llm_reply": llm_reply,
        "llm_used": llm_reply is not None,
    }
