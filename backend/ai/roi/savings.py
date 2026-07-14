"""
backend/ai/roi/savings.py
──────────────────────────
ROI Intelligence — "how many hours and how much money does the software save
this restaurant" — built for pitch/sales use, so every number here must be
traceable to a real row in the DB, not invented.

Three separate totals, deliberately never summed into one figure:
  1. hours_saved      — admin/analysis time automated away (AgentMessage +
                         AgentExecution activity), converted to money using
                         this restaurant's own StaffMember.hourly_rate.
  2. money_captured    — extra revenue/margin the restaurant actually
                         realized by approving an AI recommendation
                         (PricingRecommendation.status == APPROVED). This is
                         the only "already happened, caused by the AI" money
                         figure in the system.
  3. opportunities     — money the AI has already found but the owner hasn't
                         (yet) acted on: no-show revenue at risk, overtime
                         cost, kitchen bottleneck impact. Forward-looking, not
                         realized — kept separate so the pitch never overstates
                         what's already been captured.

`orchestrator_turn` AgentMessage rows are internal LLM-call metering (empty
recipient/body, see brain.py's `[meter]` rows and test_dashboard.py) — not a
real customer interaction, excluded here for the same reason the main
dashboard excludes them. `agent_failure` rows are failure notices, not
completed work, also excluded.
"""

from sqlalchemy.orm import Session
from datetime import timedelta
from collections import defaultdict
import models
from ai.analysis_clock import analysis_anchor

# ── Minutes-saved benchmarks ────────────────────────────────────────────────
# Conservative estimates of the manual-staff-time each automated action
# replaces. Kept explicit and commented (not hidden inside a formula) so the
# assumption is auditable and can be challenged/tuned per restaurant later.
MESSAGE_MINUTES_SAVED = {
    "morning_briefing":            10,  # manager compiling daily numbers by hand
    "reservation_reminder":         3,  # staff calling/texting a reminder
    "no_show_winback":              5,  # staff calling to re-engage/rebook
    "receipt":                      1,  # manually texting/printing a receipt
    "promo":                        2,  # sending one promotional message
    "campaign_winback":             2,
    "feedback_alert":               5,  # staff noticing and acting on feedback
    "slow_day_alert":               5,
    "reorder_request":              5,
    "supplier_late":                5,
    "stock_depleted":               5,
    "orchestrated_stock_critical":  5,
}
DEFAULT_MESSAGE_MINUTES = 3

EXCLUDED_MESSAGE_TYPES = {"orchestrator_turn", "agent_failure"}

EXECUTION_MINUTES_SAVED = {
    "pricing_intelligence":        25,  # manual competitor/margin repricing pass
    "labor_intelligence":          20,  # manual overtime/scheduling review
    "profit_intelligence":         30,  # manual contribution-margin analysis
    "inventory_predictor":         20,  # manual stock-level review
    "supply_chain_intelligence":   20,  # manual supplier performance review
}
DEFAULT_EXECUTION_MINUTES = 15

DEFAULT_HOURLY_RATE_CENTS = 25000  # KES 250/hr — used only if no staff wage data exists yet


def _time_saved_in_window(db, restaurant_id, start, end, avg_hourly_rate_cents) -> tuple[float, int]:
    """
    (hours, money_cents) of automated work completed in [start, end), using the
    same minutes-saved benchmarks as the main breakdown. Kept lean (no per-row
    breakdown) — it exists so the current 30-day figure can be compared against
    the previous 30 days for a trend, without duplicating the breakdown logic.
    """
    msgs = (
        db.query(models.AgentMessage)
        .filter(
            models.AgentMessage.restaurant_id == restaurant_id,
            models.AgentMessage.created_at >= start,
            models.AgentMessage.created_at < end,
            models.AgentMessage.message_type.notin_(EXCLUDED_MESSAGE_TYPES),
        )
        .all()
    )
    minutes = sum(
        MESSAGE_MINUTES_SAVED.get((m.message_type or "").split(":", 1)[0], DEFAULT_MESSAGE_MINUTES)
        for m in msgs
    )
    execs = (
        db.query(models.AgentExecution)
        .filter(
            models.AgentExecution.restaurant_id == restaurant_id,
            models.AgentExecution.created_at >= start,
            models.AgentExecution.created_at < end,
            models.AgentExecution.success.is_(True),
        )
        .all()
    )
    minutes += sum(
        EXECUTION_MINUTES_SAVED.get(e.agent_name, DEFAULT_EXECUTION_MINUTES) for e in execs
    )
    hours = round(minutes / 60, 1)
    return hours, round(hours * avg_hourly_rate_cents)


def _pct_change(current: float, previous: float) -> float | None:
    """Signed % change current-vs-previous. None when there's no prior baseline
    (can't honestly express a % change from zero)."""
    if not previous:
        return None
    return round((current - previous) / previous * 100, 1)


def get_roi_savings(db: Session, restaurant_id: int) -> dict:
    """Time & money the software has saved/made this restaurant, last 30 days."""
    now = analysis_anchor(db, restaurant_id)
    thirty_days_ago = now - timedelta(days=30)

    # ── 1. TIME SAVED ────────────────────────────────────────────────────────
    messages = (
        db.query(models.AgentMessage)
        .filter(
            models.AgentMessage.restaurant_id == restaurant_id,
            models.AgentMessage.created_at >= thirty_days_ago,
            models.AgentMessage.message_type.notin_(EXCLUDED_MESSAGE_TYPES),
        )
        .all()
    )
    # The send choke point logs message_type as "<type>:<channel>" (e.g.
    # promo:whatsapp) and sometimes raw. Normalise on the part before ":" so a
    # promo / win-back sent over any channel still maps to its benchmark and
    # label instead of silently falling to the default minutes.
    message_counts = defaultdict(int)
    for m in messages:
        message_counts[(m.message_type or "").split(":", 1)[0]] += 1

    message_breakdown = [
        {
            "category": mtype,
            "count": count,
            "minutes_per_action": MESSAGE_MINUTES_SAVED.get(mtype, DEFAULT_MESSAGE_MINUTES),
            "total_minutes": count * MESSAGE_MINUTES_SAVED.get(mtype, DEFAULT_MESSAGE_MINUTES),
        }
        for mtype, count in message_counts.items()
    ]

    executions = (
        db.query(models.AgentExecution)
        .filter(
            models.AgentExecution.restaurant_id == restaurant_id,
            models.AgentExecution.created_at >= thirty_days_ago,
            models.AgentExecution.success.is_(True),
        )
        .all()
    )
    execution_counts = defaultdict(int)
    for e in executions:
        execution_counts[e.agent_name] += 1

    execution_breakdown = [
        {
            "category": name,
            "count": count,
            "minutes_per_action": EXECUTION_MINUTES_SAVED.get(name, DEFAULT_EXECUTION_MINUTES),
            "total_minutes": count * EXECUTION_MINUTES_SAVED.get(name, DEFAULT_EXECUTION_MINUTES),
        }
        for name, count in execution_counts.items()
    ]

    total_minutes = sum(b["total_minutes"] for b in message_breakdown) + \
                     sum(b["total_minutes"] for b in execution_breakdown)
    hours_saved = round(total_minutes / 60, 1)

    staff = db.query(models.StaffMember).filter(
        models.StaffMember.restaurant_id == restaurant_id,
        models.StaffMember.is_active.is_(True),
        models.StaffMember.hourly_rate > 0,
    ).all()
    avg_hourly_rate_cents = (
        round(sum(s.hourly_rate for s in staff) / len(staff))
        if staff else DEFAULT_HOURLY_RATE_CENTS
    )
    hourly_rate_is_estimated = not bool(staff)

    money_saved_from_time_cents = round(hours_saved * avg_hourly_rate_cents)

    # Prior 30-day window (days 30–60 back) for a trend arrow — "is the AI saving
    # more this month than last?". Same benchmarks, priced at the same rate so the
    # comparison is apples-to-apples.
    sixty_days_ago = now - timedelta(days=60)
    prev_hours, prev_money_saved_cents = _time_saved_in_window(
        db, restaurant_id, sixty_days_ago, thirty_days_ago, avg_hourly_rate_cents
    )

    time_saved = {
        "hours_saved_30d": hours_saved,
        "money_saved_cents": money_saved_from_time_cents,
        "avg_hourly_rate_cents": avg_hourly_rate_cents,
        "hourly_rate_is_estimated": hourly_rate_is_estimated,
        "breakdown": sorted(message_breakdown + execution_breakdown, key=lambda x: -x["total_minutes"]),
        "hours_saved_prev_30d": prev_hours,
        "money_saved_prev_cents": prev_money_saved_cents,
        "hours_change_pct": _pct_change(hours_saved, prev_hours),
    }

    # ── 2. MONEY ALREADY CAPTURED (realized, caused by an approved AI rec) ──
    approved_recs = db.query(models.PricingRecommendation).filter(
        models.PricingRecommendation.restaurant_id == restaurant_id,
        models.PricingRecommendation.status == "APPROVED",
        models.PricingRecommendation.actioned_at >= thirty_days_ago,
    ).all()
    monthly_impact_cents = sum(r.monthly_impact_cents for r in approved_recs)

    # Prior-window captured (for the same trend treatment) and all-time captured
    # (the standing monthly profit uplift from EVERY price change ever approved —
    # a "since you started" figure the 30-day window alone can't show).
    prev_approved = db.query(models.PricingRecommendation).filter(
        models.PricingRecommendation.restaurant_id == restaurant_id,
        models.PricingRecommendation.status == "APPROVED",
        models.PricingRecommendation.actioned_at >= sixty_days_ago,
        models.PricingRecommendation.actioned_at < thirty_days_ago,
    ).all()
    all_approved = db.query(models.PricingRecommendation).filter(
        models.PricingRecommendation.restaurant_id == restaurant_id,
        models.PricingRecommendation.status == "APPROVED",
    ).all()
    money_captured = {
        "monthly_impact_cents": monthly_impact_cents,
        "recommendations_approved": len(approved_recs),
        "prev_monthly_impact_cents": sum(r.monthly_impact_cents for r in prev_approved),
        "change_pct": _pct_change(monthly_impact_cents, sum(r.monthly_impact_cents for r in prev_approved)),
        "all_time_monthly_impact_cents": sum(r.monthly_impact_cents for r in all_approved),
        "all_time_approved": len(all_approved),
    }

    # ── 3. OPPORTUNITIES FOUND (money the AI has flagged, not yet realized) ──
    # Each source is a separate deterministic module. They are wrapped
    # individually so one slow/failing module degrades to "that line is
    # missing" instead of taking down the whole ROI endpoint. Every value is
    # normalized to CENTS here — the frontend divides by 100 exactly once, so a
    # source that reports in whole KES (inventory: cost_per_unit is a Float in
    # KES, not cents) must be ×100 at the point it's added.
    opportunities: list[dict] = []

    def _add(source: str, label: str, cents) -> None:
        cents = int(cents or 0)
        if cents > 0:
            opportunities.append({"source": source, "label": label, "monthly_value_cents": cents})

    # Pricing recommendations the owner hasn't approved yet — money on the table.
    try:
        pending_recs = db.query(models.PricingRecommendation).filter(
            models.PricingRecommendation.restaurant_id == restaurant_id,
            models.PricingRecommendation.status == "PENDING",
        ).all()
        _add("pricing_pending", "Uncaptured margin in pending pricing recs",
             sum(r.monthly_impact_cents for r in pending_recs))
    except Exception:  # noqa: BLE001 — ROI must degrade, not crash
        pass

    # Profit leaks + portion drift (already in cents).
    try:
        from ai.profit.intelligence import get_profit_intelligence
        profit = get_profit_intelligence(db, restaurant_id)
        _add("profit_leaks", "Margin leaking from low-margin items",
             (profit.get("summary") or {}).get("total_leak_amount"))
        _add("portion_drift", "Lost to portion / discount drift",
             sum(d.get("estimated_monthly_leak", 0) for d in (profit.get("portion_drift") or [])))
    except Exception:  # noqa: BLE001
        pass

    # Inventory waste (cost_per_unit is a Float in KES → ×100 to cents).
    try:
        from ai.inventory_predictor import get_inventory_predictions
        inv = get_inventory_predictions(db, restaurant_id)
        waste_kes = sum(
            (p.get("waste_qty_30d") or 0) * (p.get("cost_per_unit") or 0)
            for p in (inv.get("predictions") or [])
        )
        _add("inventory_waste", "Stock lost to waste / spoilage", round(waste_kes * 100))
    except Exception:  # noqa: BLE001
        pass

    # Reservation no-shows + overbooking recovery (already in cents).
    try:
        from ai.reservation_optimizer import get_reservation_insights
        res = get_reservation_insights(db, restaurant_id)
        _add("no_show_prevention", "Revenue at risk from no-shows",
             (res.get("revenue_impact") or {}).get("estimated_revenue_lost"))
        _add("overbooking_recovery", "Recoverable via smarter overbooking",
             (res.get("overbooking") or {}).get("potential_monthly_recovery"))
    except Exception:  # noqa: BLE001
        pass

    # Overtime cost flagged (already in cents).
    try:
        from ai.labor.intelligence import get_labor_intelligence
        labor = get_labor_intelligence(db, restaurant_id)
        _add("overtime_reduction", "Overtime cost flagged for review",
             (labor.get("summary") or {}).get("overtime_cost_30d"))
    except Exception:  # noqa: BLE001
        pass

    opportunities.sort(key=lambda o: -o["monthly_value_cents"])

    # ── 4. KITCHEN CAPACITY (non-monetary — a "do more with the same staff"
    # story). Deliberately NOT converted to money: turning ticket-speed into
    # KES needs assumptions the app can't verify, so it's surfaced as
    # throughput/bottleneck facts the KDS module already computes. ────────────
    capacity = None
    try:
        from ai.kds_intelligence import get_kds_intelligence
        kds = get_kds_intelligence(db, restaurant_id)
        thr = kds.get("throughput") or {}
        bottlenecks = kds.get("bottlenecks") or []
        if thr.get("total_completed"):
            capacity = {
                "avg_order_minutes": thr.get("avg_order_completion_minutes"),
                "orders_per_day": thr.get("orders_per_day"),
                "bottlenecks_found": len(bottlenecks),
                # Total systemic delay the AI has flagged as reclaimable.
                "reclaimable_delay_minutes": round(sum(b.get("impact_score", 0) for b in bottlenecks), 1),
            }
    except Exception:  # noqa: BLE001
        pass

    # ── 5. NET ROI (is the AI worth what it costs?) ──────────────────────────
    # AI cost = this restaurant's LLM token spend over the window, priced by the
    # same static cost model AI-Ops uses. Value delivered = the two "real money"
    # figures already on this page (time saved + profit captured) — opportunities
    # are deliberately excluded because they aren't realized yet. Kept as a ratio,
    # never a blended total, so it stays honest.
    ai_cost_cents = 0
    try:
        from ai.cost_model import cost_kes_cents
        token_rows = db.query(models.TokenUsage).filter(
            models.TokenUsage.restaurant_id == restaurant_id,
            models.TokenUsage.created_at >= thirty_days_ago,
        ).all()
        ai_cost_cents = sum(
            cost_kes_cents(t.llm_model, t.input_tokens or 0, t.output_tokens or 0)
            for t in token_rows
        )
    except Exception:  # noqa: BLE001 — ROI must degrade, not crash
        pass

    value_delivered_cents = money_saved_from_time_cents + monthly_impact_cents
    economics = {
        "ai_cost_cents": ai_cost_cents,
        "value_delivered_cents": value_delivered_cents,
        # "Every KES 1 spent on AI returned KES X." None when there's no metered
        # AI spend yet (can't divide by zero — the frontend shows this honestly).
        "roi_multiple": round(value_delivered_cents / ai_cost_cents, 1) if ai_cost_cents > 0 else None,
    }

    # ── 6. ANNUAL RUN-RATE (at the current pace) ─────────────────────────────
    # Simple ×12 annualization of the two monthly figures. Labelled "at current
    # pace" in the UI — a projection, not a promise.
    projection = {
        "annual_hours_saved": round(hours_saved * 12),
        "annual_money_saved_cents": round(money_saved_from_time_cents * 12),
        "annual_captured_cents": round(monthly_impact_cents * 12),
    }

    return {
        "window_days": 30,
        "time_saved": time_saved,
        "money_captured": money_captured,
        "opportunities": opportunities,
        "capacity": capacity,
        "economics": economics,
        "projection": projection,
    }
