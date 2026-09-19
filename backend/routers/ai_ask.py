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
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import models
from database import get_db
from auth import require_staff_role
from routers.reports import _grounded_reply
from routers.overview import _restaurant_id

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


# Question -> module routing.
#
# Scored, not first-match. The previous version walked an ordered list and took
# the first rule with any keyword hit, which made generic words upstream beat
# specific words downstream: "today" under revenue captured "Who is working
# today?" (staff) and "How many customers are expected today?" (bookings), and
# "increase" under pricing captured "How can I increase my profit?". Eight of
# the OS page's own 78 suggested questions landed on the wrong module — the
# owner pressed a button and got an answer about something else.
#
# Now every rule is scored by its LONGEST matching keyword and the highest wins,
# so a specific phrase beats an incidental word regardless of rule order.
# "Why is my kitchen slow?" scores kitchen(7) over revenue(4) and routes to the
# kitchen; "Which days are slow?" matches only revenue.
#
# Some questions are genuinely ambiguous and that is fine — best-sellers are
# menu engineering even though the UI groups them under Sales, and a stuck
# order is a kitchen question. tests/test_os_question_routing.py pins every
# built-in question and names the ones with more than one defensible answer.
_ROUTING_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("stock", ("run out", "running out", "about to run out", "stock", "stock-out", "waste",
               "wastage", "wasting", "reorder", "re-order", "expir", "spoil", "inventory",
               "low stock", "shortage", "ingredient")),
    ("bookings", ("book", "booking", "reservation", "reserve", "no-show", "no show",
                  "not showing", "showing up", "covers", "waitlist", "table", "guest",
                  "customers expected", "how many customers")),
    ("kitchen", ("kitchen", "prep", "preparation", "station", "backed up", "bottleneck",
                 "ticket", "take too long", "taking too long")),
    ("staff", ("staff", "labour", "labor", "shift", "who is working", "who's working",
               "understaff", "overstaff", "schedule", "rota", "overtime", "productivity",
               "worked the most")),
    ("pricing", ("price", "pricing", "underpriced", "overpriced", "price increase",
                 "charge more", "covering my costs", "prices compare")),
    ("menu", ("menu", "best-sell", "best sell", "selling", "sell the most", "promote",
              "dish", "remove", "worth keeping", "popular", "most money")),
    ("profit", ("profit", "margin", "losing money", "money losing", "food cost", "cost",
                "expense", "leak", "most profit")),
    ("revenue", ("sale", "sales", "revenue", "income", "forecast", "trending", "slow",
                 "busiest", "how much did i make", "takings")),
]


def _route(question: str) -> str:
    """Pick the module best matching `question`; "ops" when nothing matches."""
    q = question.lower()
    best, best_score = "ops", 0
    for module, keywords in _ROUTING_RULES:
        score = max((len(k) for k in keywords if k in q), default=0)
        if score > best_score:
            best, best_score = module, score
    return best


def _first_action(recs: list, fallback: str) -> str:
    """First recommendation's action text. Agent recommendations are dicts with
    an "action" key, but a few modules emit plain strings — handle both rather
    than indexing into recs[0] and hoping."""
    for r in recs:
        if isinstance(r, str) and r.strip():
            return r
        if isinstance(r, dict):
            action = r.get("action") or r.get("message")
            if action:
                return action
    return fallback


def _rec_steps(recs: list, limit: int) -> list[dict]:
    """Recommendations as answer-card steps, skipping any that carry no action."""
    steps = []
    for r in recs[:limit]:
        if isinstance(r, str):
            steps.append({"action": r, "why": ""})
        elif isinstance(r, dict) and (r.get("action") or r.get("message")):
            steps.append({"action": r.get("action") or r.get("message"),
                          "why": r.get("message", "") if r.get("action") else ""})
    return steps


# Every answer below reads keys the agent modules ACTUALLY return. They did
# not: _answer_profit looked for "leaks"/"issues" (the payload has
# "profit_leaks"), _answer_staff for "labor_cost_pct" (it is
# summary.labor_pct), _answer_bookings for "no_show" (it is
# no_show_analysis.no_show_rate), _answer_kitchen for "stations" (it is
# station_performance), _answer_revenue for "trend" (it is "trends"), and
# _answer_stock for "days_until_stockout"/"item_name" (they are
# days_until_depletion/name). Each mismatch resolved to None and fell through
# to a calm, confident "nothing to report" — the OS page told the owner
# everything was fine because it was reading fields that never existed.
# Verified against each module's return statement, not its docstring.


def _answer_stock(db: Session, rid: int, q: str) -> dict:
    from ai.inventory_predictor import get_inventory_predictions
    preds = get_inventory_predictions(db, rid)
    items = preds.get("predictions") or []
    soon = [p for p in items
            if p.get("days_until_depletion") is not None and p["days_until_depletion"] <= 7]
    low = [p for p in items if p.get("status") in ("critical", "low", "reorder")]
    focus = soon or low
    if focus:
        names = ", ".join(p.get("name", "?") for p in focus[:3])
        finding = (f"{len(soon)} item(s) projected to run out within a week: {names}."
                   if soon else f"{len(low)} item(s) at or below reorder point: {names}.")
        why = ("Based on recorded usage velocity against current quantity on hand."
               if soon else
               "Current quantity is at or below the reorder threshold. Stockout timing is not established.")
        impact = "Avoids emergency buying at higher prices and mid-service menu gaps"
        rec = f"Raise today's order for {focus[0].get('name', 'the affected items')} and confirm the next delivery slot."
        steps = [
            {"action": f"Reorder {p.get('name')}",
             "why": (f"{p['days_until_depletion']} days of stock left at recorded usage"
                     if p.get("days_until_depletion") is not None
                     else f"At {p.get('current_stock')} {p.get('unit', '')}, reorder point {p.get('reorder_point')}")}
            for p in focus[:4]
        ]
    else:
        finding = "No low-stock or imminent stockout candidates in the recorded data."
        why = "Every tracked item is above its reorder point with usage history to support it."
        impact = "—"
        rec = "Nothing to reorder on stock levels alone today."
        steps = []
    return {"finding": finding, "why": why, "impact": impact, "recommendation": rec,
            "module": "reorder", "steps": steps,
            "data": {"candidates": len(focus), "stockout_timing_available": bool(soon),
                     "narrative_allowed": bool(soon)}}


def _answer_revenue(db: Session, rid: int, q: str) -> dict:
    from ai.revenue_forecaster import get_revenue_forecast
    from routers.overview import _summarize, _eat_range  # EAT-day truth
    start, end = _eat_range("today")
    core = _summarize(db, rid, start, end)
    trends, anomalies, forecast = {}, [], []
    try:
        fc = get_revenue_forecast(db, rid)
        trends = fc.get("trends") or {}
        anomalies = fc.get("anomalies") or []
        forecast = fc.get("forecast") or []
    except Exception:  # noqa: BLE001 — today's figure stands without the forecast
        pass

    finding = f"Revenue today is {_money(core['revenue'] * 100)} across {core['orders']} paid orders."
    # An anomaly is the most useful thing the forecaster knows. It was computed
    # on every call and never surfaced anywhere the owner could see it.
    if anomalies:
        a0 = anomalies[0]
        finding += (f" {a0['date']} was a {a0['type']} at {a0['deviation_pct']:+.1f}% "
                    f"versus the period average.")
    why = ("Paid, non-cancelled orders created during the Nairobi calendar day so far. "
           "This is not payment cash flow.")
    # core["revenue"] is already KES (overview's _summarize converts cents→KES);
    # avg_order must stay in KES — multiplying by 100 again showed absurd figures
    # (verified in browser 2026-09-12: "KSh 199,467" instead of KSh 1,995).
    impact = (f"Average order {_money(core['revenue'] * 100 / core['orders'])} per order"
              if core["orders"] else "Average order — no orders yet today")
    wow = trends.get("week_over_week_growth")
    if wow is not None:
        rec = (f"Week-over-week revenue is {wow:+.1f}%. "
               + ("Hold the current mix." if wow >= 0 else "Review what changed in the last seven days."))
    else:
        rec = "Compare against the 7-day trend on Home to see if today is ahead or behind."
    steps = []
    for a in anomalies[:3]:
        steps.append({"action": f"Check {a['date']}: {a['type']} of {a['deviation_pct']:+.1f}%",
                      "why": f"Revenue {_money(a['revenue'] * 100)} against an expected {_money(a['expected'] * 100)}"})
    if not steps and isinstance(forecast, list):
        for day in forecast[:3]:
            if isinstance(day, dict):
                steps.append({"action": f"{day.get('date', 'Next')}: forecast {_money((day.get('predicted_revenue') or 0) * 100)}"})
    return {"finding": finding, "why": why, "impact": impact, "recommendation": rec,
            "module": "revenue", "steps": steps,
            "data": {"today": core, "anomalies_found": len(anomalies)}}


def _answer_bookings(db: Session, rid: int, q: str) -> dict:
    from ai.reservation_optimizer import get_reservation_insights
    ins = get_reservation_insights(db, rid)
    ns = ins.get("no_show_analysis") or {}
    rate = ns.get("no_show_rate")
    total = ns.get("total_reservations") or 0
    lost = (ins.get("revenue_impact") or {}).get("estimated_revenue_lost")
    recs = ins.get("recommendations") or []

    if total == 0:
        finding = "No reservations recorded in the analysed period."
        why = "No-show and utilisation figures need booking history to compute."
        impact = "—"
    else:
        finding = (f"No-show rate is {rate}% across {total} reservation(s); "
                   f"completion rate {ns.get('completion_rate', '—')}%.")
        why = ("Computed from your reservation history: completion rate, lead time "
               "and party-size patterns.")
        impact = _money(lost) if lost else "Protects table availability"
    rec = _first_action(recs, "Enable deposit requests for peak slots.")
    steps = _rec_steps(recs, 4)
    return {"finding": finding, "why": why, "impact": impact, "recommendation": rec,
            "module": "reservations", "steps": steps,
            "data": {"no_show_rate": rate, "total_reservations": total}}


def _answer_kitchen(db: Session, rid: int, q: str) -> dict:
    from ai.kds_intelligence import get_kds_intelligence
    kds = get_kds_intelligence(db, rid)
    bottlenecks = kds.get("bottlenecks") or []
    stations = kds.get("station_performance") or []
    if bottlenecks:
        b0 = bottlenecks[0]
        finding = (f"{b0['station']} is the bottleneck at {b0['avg_minutes']} min average, "
                   f"{b0['above_avg_by']} min above the kitchen average of {b0['kitchen_avg']} "
                   f"({b0['severity']}).")
    elif stations:
        slowest = max(stations, key=lambda st: st.get("avg_minutes") or 0)
        finding = (f"No station is above the bottleneck threshold. Slowest is "
                   f"{slowest.get('station')} at {slowest.get('avg_minutes')} min average.")
    else:
        finding = "No kitchen timing data recorded yet for this period."
    why = "From recorded prep times per item and per station."
    impact = "Protects ticket times during rush"
    recs = kds.get("recommendations") or []
    rec = _first_action(recs, "Keep the current line setup.")
    steps = _rec_steps(recs, 4)
    return {"finding": finding, "why": why, "impact": impact, "recommendation": rec,
            "module": "kitchen", "steps": steps,
            "data": {"bottlenecks": len(bottlenecks), "stations": len(stations)}}


def _answer_staff(db: Session, rid: int, q: str) -> dict:
    from ai.labor.intelligence import get_labor_intelligence
    labor = get_labor_intelligence(db, rid)
    summary = labor.get("summary") or {}
    pct = summary.get("labor_pct")
    shifts = summary.get("shifts_logged") or 0
    recs = labor.get("recommendations") or []

    if not shifts:
        finding = "No shifts logged in the last 30 days, so labour cost cannot be measured."
        why = "Labour percentage needs clocked shifts to divide against revenue."
        impact = "—"
    else:
        status = summary.get("labor_status", "")
        finding = (f"Labour is {pct}% of revenue across {shifts} logged shift(s) "
                   f"— {'within' if status == 'HEALTHY' else 'above'} the healthy band.")
        overtime = summary.get("overtime_hours_30d") or 0
        if overtime:
            finding += f" {overtime} overtime hour(s) recorded, costing {_money(summary.get('overtime_cost_30d'))}."
        why = "From clocked shifts against revenue over the last 30 days."
        impact = f"Sales per labour hour: {_money(summary.get('sales_per_hour'))}"
    rec = _first_action(recs, "Align the longest shifts with your peak windows.")
    steps = _rec_steps(recs, 4)
    return {"finding": finding, "why": why, "impact": impact, "recommendation": rec,
            "module": "labor", "steps": steps,
            "data": {"labor_pct": pct, "shifts_logged": shifts}}


def _answer_menu(db: Session, rid: int, q: str) -> dict:
    from ai.menu_engineer import get_menu_engineering
    me = get_menu_engineering(db, rid)
    summary = me.get("summary") or {}
    matrix = me.get("matrix") or []
    # summary.stars/dogs are COUNTS, not lists. `len()` on an integer raised
    # TypeError here, which the route swallowed into a generic failure — the
    # item names live in `matrix`, keyed by classification.
    star_items = [m for m in matrix if m.get("classification") == "Star"]
    dog_items = [m for m in matrix if m.get("classification") == "Dog"]
    puzzle_items = [m for m in matrix if m.get("classification") == "Puzzle"]

    if not matrix:
        finding = "Not enough order history yet to classify the menu."
    else:
        finding = (f"Menu mix across {summary.get('total_items', len(matrix))} item(s): "
                   f"{len(star_items)} Star, {len(puzzle_items)} Puzzle, {len(dog_items)} Dog. "
                   f"Optimisation score {summary.get('menu_optimization_score', '—')}/100.")
    why = "Menu engineering classifies items by popularity against margin (Star, Plowhorse, Puzzle, Dog)."
    impact = (f"Average food cost {summary.get('avg_food_cost_pct')}%, average margin "
              f"{summary.get('avg_margin_pct')}%") if summary else "—"
    recs = me.get("recommendations") or []
    rec = _first_action(recs, "Keep collecting order data for classification.")
    steps = [{"action": f"Promote {m.get('item_name') or m.get('name')}",
              "why": f"Star — {m.get('margin_pct', '?')}% margin at {m.get('qty_sold', '?')} sold"}
             for m in star_items[:3]]
    steps += [{"action": f"Rework or cut {m.get('item_name') or m.get('name')}",
               "why": f"Dog — {m.get('margin_pct', '?')}% margin at {m.get('qty_sold', '?')} sold"}
              for m in dog_items[:2]]
    return {"finding": finding, "why": why, "impact": impact, "recommendation": rec,
            "module": "menu", "steps": steps,
            "data": {"stars": len(star_items), "dogs": len(dog_items)}}


def _answer_pricing(db: Session, rid: int, q: str) -> dict:
    from ai.pricing.recommendations import get_pricing_intelligence
    pi = get_pricing_intelligence(db, rid)
    recs = pi.get("recommendations") or []
    summary = pi.get("summary") or {}
    opportunity = summary.get("total_revenue_opportunity_cents") or 0

    if recs:
        r0 = recs[0]
        finding = (f"{len(recs)} pricing change(s) recommended. Top: {r0['item_name']} "
                   f"from {_money(r0['current_price'])} to {_money(r0['suggested_price'])} "
                   f"({r0['type'].lower()}) — {r0['reason']}.")
        impact = f"{_money(opportunity)}/month across all recommendations"
        rec = (f"Approve the {r0['item_name']} change on Home to apply it "
               f"({_money(r0['monthly_impact_cents'])}/month).")
    else:
        finding = "No pricing changes recommended right now."
        impact = "—"
        rec = "Margins are inside the target band on every item with enough sales history."
    why = ("Item margins against the 40% floor and recent selling velocity, "
           "with a 7-day cooldown after each change.")
    steps = [{"action": (f"{r['item_name']}: {_money(r['current_price'])} → "
                         f"{_money(r['suggested_price'])} ({r['price_change_pct']:+.1f}%)"),
              "why": r["reason"]}
             for r in recs[:4]]
    return {"finding": finding, "why": why, "impact": impact, "recommendation": rec,
            "module": "pricing", "steps": steps,
            "data": {"open_recommendations": len(recs), "opportunity_cents": opportunity}}


def _answer_profit(db: Session, rid: int, q: str) -> dict:
    from ai.profit.intelligence import get_profit_intelligence
    pi = get_profit_intelligence(db, rid)
    summary = pi.get("summary") or {}
    leaks = pi.get("profit_leaks") or []
    uncosted = pi.get("uncosted_items") or []
    total_leak = summary.get("total_leak_amount") or 0
    coverage = summary.get("cost_coverage_pct")

    if leaks:
        l0 = leaks[0]
        finding = (f"Biggest leak: {l0['item_name']} at {l0['current_margin_pct']}% margin, "
                   f"{_money(l0['monthly_leak_cents'])}/month. "
                   f"{len(leaks)} item(s) below the {40}% floor.")
    elif uncosted:
        finding = (f"No measurable leaks, but {len(uncosted)} item(s) have no cost price — "
                   f"{_money(summary.get('uncosted_revenue_30d'))} of sales cannot be checked.")
    else:
        finding = (f"No items below the margin floor. Gross margin "
                   f"{summary.get('gross_margin_pct', '—')}%, food cost "
                   f"{summary.get('food_cost_pct', '—')}%.")
    why = "Per-item contribution margin against the critical floor, over the last 30 days."
    if coverage is not None and coverage < 100:
        why += f" Covers {coverage}% of revenue — the rest has no cost price entered."
    impact = _money(total_leak) if total_leak else "—"
    recs = pi.get("recommendations") or []
    rec = _first_action(recs, "Maintain current cost controls.")
    steps = [{"action": l["action"], "why": f"{l['item_name']} at {l['current_margin_pct']}% margin"}
             for l in leaks[:4]]
    if not steps:
        steps = _rec_steps(recs, 4)
    return {"finding": finding, "why": why, "impact": impact, "recommendation": rec,
            "module": "profit", "steps": steps,
            "data": {"leaks": len(leaks), "uncosted_items": len(uncosted),
                     "cost_coverage_pct": coverage}}


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
    rid = _restaurant_id(db, user)
    if not rid:
        raise HTTPException(404, "No restaurant found for this account")
    module = _route(question)
    try:
        card = _HANDLERS[module](db, rid, question)
    except Exception:  # Do not substitute unrelated facts or expose internal errors.
        card = _unavailable_card(module)
    return card


# ─── LLM chat (real-time, OpenRouter) ────────────────────────────────────────

class HistoryTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatBody(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    history: list[HistoryTurn] = Field(default_factory=list, max_length=6)


def _unavailable_card(module: str) -> dict:
    return {
        "finding": "The data needed to answer this question is unavailable.",
        "why": "The requested analysis could not be completed. No conclusion was verified.",
        "impact": "Not available",
        "recommendation": "Retry the question or review the source records in Macsoft.",
        "module": module, "steps": [], "data": {"available": False},
    }


@router.post("/chat")
def chat_llm(body: ChatBody, db: Session = Depends(get_db),
             user: models.User = Depends(require_staff_role())):
    """Real-time conversational answer: routes the question to the right ai/
    module for GROUNDED DATA, then lets the LLM (OpenRouter) write a
    conversational reply from that data. The LLM never invents numbers — its
    prompt contains only the module's real figures, and the raw data ships
    alongside so the client can show both."""
    rid = _restaurant_id(db, user)
    if not rid:
        raise HTTPException(404, "No restaurant found for this account")

    module = _route(body.question)
    try:
        card = _HANDLERS[module](db, rid, body.question)
    except Exception:  # Grounding failure must be visible, not replaced by another topic.
        card = _unavailable_card(module)

    from ai import llm_client
    llm_reply = None
    if (card.get("data", {}).get("available") is not False
            and card.get("data", {}).get("narrative_allowed") is not False
            and llm_client.is_available()):
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
        messages = [turn.model_dump() for turn in body.history] + [
            {"role": "user", "content": body.question}]
        try:
            llm_reply = llm_client.chat(
                messages, system=system, max_tokens=400, tier="medium")
            llm_reply = _grounded_reply(llm_reply, context)
        except Exception:  # LLM failure never exposes provider diagnostics to the client.
            llm_reply = None

    return {
        "module": module,
        "grounded": card,
        "llm_reply": llm_reply,
        "llm_used": llm_reply is not None,
    }
