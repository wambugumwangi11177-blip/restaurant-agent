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
    message_counts = defaultdict(int)
    for m in messages:
        message_counts[m.message_type] += 1

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

    time_saved = {
        "hours_saved_30d": hours_saved,
        "money_saved_cents": money_saved_from_time_cents,
        "avg_hourly_rate_cents": avg_hourly_rate_cents,
        "hourly_rate_is_estimated": hourly_rate_is_estimated,
        "breakdown": sorted(message_breakdown + execution_breakdown, key=lambda x: -x["total_minutes"]),
    }

    # ── 2. MONEY ALREADY CAPTURED (realized, caused by an approved AI rec) ──
    approved_recs = db.query(models.PricingRecommendation).filter(
        models.PricingRecommendation.restaurant_id == restaurant_id,
        models.PricingRecommendation.status == "APPROVED",
        models.PricingRecommendation.actioned_at >= thirty_days_ago,
    ).all()
    money_captured = {
        "monthly_impact_cents": sum(r.monthly_impact_cents for r in approved_recs),
        "recommendations_approved": len(approved_recs),
    }

    # ── 3. OPPORTUNITIES FOUND (flagged, not yet realized) ──────────────────
    opportunities = []

    from ai.reservation_optimizer import get_reservation_insights
    res = get_reservation_insights(db, restaurant_id)
    revenue_impact = res.get("revenue_impact") or {}
    if revenue_impact.get("estimated_revenue_lost"):
        opportunities.append({
            "source": "no_show_prevention",
            "label": "Revenue at risk from no-shows",
            "monthly_value_cents": revenue_impact["estimated_revenue_lost"],
        })
    overbooking = res.get("overbooking") or {}
    if overbooking.get("potential_monthly_recovery"):
        opportunities.append({
            "source": "overbooking_recovery",
            "label": "Recoverable via smarter overbooking",
            "monthly_value_cents": overbooking["potential_monthly_recovery"],
        })

    from ai.labor.intelligence import get_labor_intelligence
    labor = get_labor_intelligence(db, restaurant_id)
    overtime_cost = (labor.get("summary") or {}).get("overtime_cost_30d") or 0
    if overtime_cost:
        opportunities.append({
            "source": "overtime_reduction",
            "label": "Overtime cost flagged for review",
            "monthly_value_cents": overtime_cost,
        })

    return {
        "window_days": 30,
        "time_saved": time_saved,
        "money_captured": money_captured,
        "opportunities": opportunities,
    }
