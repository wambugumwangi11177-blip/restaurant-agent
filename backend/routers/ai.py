"""
backend/routers/ai.py
──────────────────────
Analytics & Recommendations Router — exposes the deterministic analytics/
recommendation modules in ai/ via REST endpoints. These are rule-based
statistics and thresholds, not LLM-backed — see directives/012_agentic_roadmap.md's
standing rule on labeling AI-vs-deterministic honestly. The only LLM-backed
code in this project is ai/whatsapp/orchestrator.py (Phase 2).

Endpoints:
  GET  /ai/pricing                    → pricing intelligence (SURGE / REPRICE / STIMULATE)
  POST /ai/pricing/{rec_id}/approve   → approve a pricing recommendation
  POST /ai/pricing/{rec_id}/reject    → reject a pricing recommendation
  GET  /ai/labor                      → labor cost analytics + recommendations
  GET  /ai/inventory                  → inventory health + restock predictions
  GET  /ai/profit                     → profit intelligence (contribution margins, leaks, drift)
  GET  /ai/supply-chain               → supplier performance + purchase order recommendations
  GET  /ai/roi                        → hours/money saved by automation, money captured, opportunities found

/ai/profit and /ai/supply-chain wired 2026-07-07: ai/profit/intelligence.py and
ai/supply_chain/intelligence.py were real, complete, working modules (verified against
real production data) with zero route ever exposing them — found auditing which ai/*
modules were actually reachable vs orphaned. See
directives/013_production_readiness_roadmap.md.

Note: /ai/dashboard, /ai/menu-engineering, /ai/revenue-forecast, and
/ai/reservation-insights are NOT defined here — they're served by
routers/analytics.py (registered first in main.py, so it wins routing ties).
This file used to duplicate those 4 routes with a second, divergent
implementation that was silently unreachable dead code — removed 2026-07-07
after finding it was still being read/edited as if live.
"""

import logging
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from database import get_db
from auth import require_role, require_staff_role
import models
import schemas
from routers.deps import get_or_create_restaurant

logger = logging.getLogger("ai.router")

router = APIRouter(prefix="/ai", tags=["ai"])

# Directive 015's matrix for `ai`/`ai-ops`: RW = Owner only, R = Manager +
# Controller. Applied by HTTP verb below — GET (insight) routes loosen to
# _AI_READ; POST routes that trigger a real action (approve a price change,
# run a workflow step, send a campaign) stay Owner-only, since the matrix
# grants no one but Owner write access here. `marketing` is the one
# exception — its matrix row gives Manager RW, not just R — so its POST
# routes use _MARKETING_WRITE instead of staying Owner-only.
_AI_READ = (models.StaffRole.MANAGER, models.StaffRole.CONTROLLER)
_MARKETING_WRITE = (models.StaffRole.MANAGER,)


def _safe_run(agent_name: str, restaurant_id: int, fn, *args, **kwargs):
    """
    Run an AI function; return error dict on failure instead of crashing.
    Emits AGENT_FAILED — subscribed to by executive.py (tracks repeated
    failures for the same agent) but nothing ever emitted it, found
    2026-07-07 auditing the event orchestration end to end.
    """
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        logger.error(f"AI module error: {e}", exc_info=True)
        from events.bus import emit_async, EventType
        emit_async(EventType.AGENT_FAILED, {
            "agent_name": agent_name,
            "restaurant_id": restaurant_id,
            "error": str(e),
        })
        return {"error": str(e), "available": False}


# ─────────────────────────────────────────────────────────────────────────────
# PRICING INTELLIGENCE
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/pricing")
async def ai_pricing(
    narrate: bool = True,
    current_user: models.User = Depends(require_staff_role(*_AI_READ)),
    db: Session = Depends(get_db),
):
    """
    Pricing intelligence: SURGE, REPRICE, STIMULATE recommendations.

    Numbers are deterministic. When an LLM provider is set (and narrate=true) a
    `narrative` block is attached — pricing runs on the MEDIUM model tier since
    it's a money decision (see ai/reasoning/narrator.py's task registry), and
    every figure it cites is grounding-checked before it's returned.
    """
    restaurant = get_or_create_restaurant(db, current_user)

    from ai.pricing.recommendations import get_pricing_intelligence, sync_pending_recommendations
    data = await run_in_threadpool(_safe_run, "pricing_intelligence", restaurant.id, get_pricing_intelligence, db, restaurant.id)

    # The analysis above is read-only and its recommendations carry no persisted
    # id — so nothing could be approved. Materialize them into PENDING rows and
    # swap in the persisted list (each with an `id` + `status`) so the UI's
    # approve/reject buttons have something to act on. Guarded: a failure here
    # must degrade to the id-less recs, never take down the working payload.
    if isinstance(data, dict) and data.get("available") is not False and "recommendations" in data:
        try:
            data["recommendations"] = sync_pending_recommendations(
                db, restaurant.id, data["recommendations"]
            )
        except Exception:  # noqa: BLE001 — degrade, don't 500
            db.rollback()
            logger.exception("sync_pending_recommendations failed for restaurant %s", restaurant.id)

    # narrate() drives a synchronous, blocking LLM SDK call. This route is async,
    # so run it off the event loop or the whole worker stalls for the round-trip.
    from ai.reasoning import attach_narrative
    data = await run_in_threadpool(attach_narrative, data, "pricing", restaurant.id, narrate)

    return data


@router.post("/pricing/{rec_id}/approve")
async def approve_pricing_rec(
    rec_id: int,
    current_user: models.User = Depends(require_role(models.Role.ADMIN)),
    db: Session = Depends(get_db),
):
    """Approve a pricing recommendation — updates menu item price immediately."""
    restaurant = get_or_create_restaurant(db, current_user)
    from ai.pricing.recommendations import approve_recommendation
    return approve_recommendation(db, rec_id, restaurant.id, approved_by=current_user.email)


@router.post("/pricing/{rec_id}/reject")
async def reject_pricing_rec(
    rec_id: int,
    body: schemas.PricingRejectBody = schemas.PricingRejectBody(),
    current_user: models.User = Depends(require_role(models.Role.ADMIN)),
    db: Session = Depends(get_db),
):
    """Reject a pricing recommendation."""
    restaurant = get_or_create_restaurant(db, current_user)
    from ai.pricing.recommendations import reject_recommendation
    return reject_recommendation(db, rec_id, restaurant.id, body.reason)


# ─────────────────────────────────────────────────────────────────────────────
# DECISION INTELLIGENCE — every agent's recommendations, ranked into one stream
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/decisions")
async def ai_decisions(
    narrate: bool = True,
    current_user: models.User = Depends(require_staff_role(*_AI_READ)),
    db: Session = Depends(get_db),
):
    """
    Unified, ranked Decision Intelligence: pulls recommendations from every
    deterministic agent (pricing, inventory, supply-chain, menu, labor,
    marketing), normalizes them into one `Decision` schema, and ranks them
    best-first by impact / confidence / risk / effort.

    Numbers are deterministic. When an LLM provider is set (and narrate=true) a
    grounded `narrative` block is attached — it interprets the ranking, it never
    recomputes the scores or invents figures.
    """
    restaurant = get_or_create_restaurant(db, current_user)

    from ai.decisions import get_ranked_decisions
    data = await run_in_threadpool(_safe_run, "decision_intelligence", restaurant.id, get_ranked_decisions, db, restaurant.id)

    from ai.reasoning import attach_narrative
    data = await run_in_threadpool(attach_narrative, data, "decisions", restaurant.id, narrate)

    return data


# ─────────────────────────────────────────────────────────────────────────────
# STRATEGY — the goal-driven CEO agent (Phase 3)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/strategy")
async def ai_strategy(
    body: schemas.StrategyGoalBody,
    current_user: models.User = Depends(require_role(models.Role.ADMIN)),
    db: Session = Depends(get_db),
):
    """
    Goal-driven strategy: give a goal ("increase monthly profit by KES 100,000")
    and get back ONE prioritized plan. When the CEO agent is enabled and an LLM
    provider is configured it consults the specialist agents + simulator + graph
    as read-only tools and narrates a grounded, sequenced plan; otherwise it
    degrades to the deterministic top-ranked decisions. Read-only — applying any
    step still goes through the existing approval endpoints.

    Body: {"goal": "...", "timeframe": "this quarter"}
    """
    restaurant = get_or_create_restaurant(db, current_user)
    goal = body.goal
    timeframe = body.timeframe

    # Blocking LLM tool loop → keep it off the event loop (see /ai/pricing).
    from ai.orchestrator.strategist import run_strategy
    return await run_in_threadpool(
        _safe_run, "strategist", restaurant.id, run_strategy, db, restaurant.id, goal, timeframe
    )


@router.post("/strategy/plan")
async def ai_strategy_plan(
    body: schemas.StrategyPlanBody,
    current_user: models.User = Depends(require_role(models.Role.ADMIN)),
    db: Session = Depends(get_db),
):
    """
    Autonomous planning (Phase 9): a time-phased, monitored plan for a goal — a
    ranked decision per week, each with a scheduled check-in and (for price moves)
    a simulation of the expected effect. Deterministic; always available.

    Body: {"goal": "...", "horizon_weeks": 4}
    """
    restaurant = get_or_create_restaurant(db, current_user)
    goal = body.goal
    weeks = body.horizon_weeks
    from ai.orchestrator.strategist import plan
    return _safe_run("strategist", restaurant.id, plan, db, restaurant.id, goal, weeks)


@router.get("/feedback")
async def ai_feedback(
    days: int = 14,
    current_user: models.User = Depends(require_staff_role(*_AI_READ)),
    db: Session = Depends(get_db),
):
    """
    Self-evaluation feedback loop (Phase 9): classifies recently-scored
    predictions (worked / acceptable / missed, and why), and reports the derived
    per-agent reliability the Decision ranking uses. Read-only.
    """
    restaurant = get_or_create_restaurant(db, current_user)
    days = min(max(days, 1), 90)
    from ai.evaluation.feedback import run_feedback_cycle
    return _safe_run("feedback_loop", restaurant.id, run_feedback_cycle, db, restaurant.id, days)


# ─────────────────────────────────────────────────────────────────────────────
# MARKETPLACE / PLUGINS — third-party agents (Phase 11)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/plugins")
async def ai_plugins_list(
    current_user: models.User = Depends(require_staff_role(*_AI_READ)),
):
    """List registered marketplace plugins (name, author, capabilities, scopes)."""
    from ai.plugins import registry
    return {"plugins": registry.list()}


@router.post("/plugins/{name}/invoke")
async def ai_plugin_invoke(
    name: str,
    body: schemas.PluginInvokeBody = schemas.PluginInvokeBody(),
    current_user: models.User = Depends(require_role(models.Role.ADMIN)),
    db: Session = Depends(get_db),
):
    """
    Invoke a registered plugin behind the SDK guardrails (read-only context,
    declared scopes, approval-gated mutation). Body: {"payload": {...},
    "approved": bool}. A mutating plugin returns requires_approval until approved.
    """
    restaurant = get_or_create_restaurant(db, current_user)
    from ai.plugins import registry
    return _safe_run("plugin_sdk", restaurant.id, registry.invoke, name, db, restaurant.id, body.payload, body.approved)


# ─────────────────────────────────────────────────────────────────────────────
# WORKFLOW ENGINE — durable, multi-step agentic processes (Phase 8)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/workflows/templates")
async def ai_workflow_templates(
    current_user: models.User = Depends(require_staff_role(*_AI_READ)),
):
    """List the available workflow templates that can be started."""
    from ai.workflows import template_names
    return {"templates": template_names()}


@router.post("/workflows/{template}/start")
async def ai_workflow_start(
    template: str,
    current_user: models.User = Depends(require_role(models.Role.ADMIN)),
    db: Session = Depends(get_db),
):
    """
    Start a durable workflow run from a template. Runs auto steps until it
    reaches a human-approval or wait-for-external pause, then returns the run
    state (id + steps) for the owner to act on.
    """
    restaurant = get_or_create_restaurant(db, current_user)
    from ai.workflows import start_workflow
    return _safe_run("workflow_engine", restaurant.id, start_workflow, db, restaurant.id, template)


@router.get("/workflows/{run_id}")
async def ai_workflow_get(
    run_id: int,
    current_user: models.User = Depends(require_staff_role(*_AI_READ)),
    db: Session = Depends(get_db),
):
    """Fetch one workflow run's current state (steps, status, context)."""
    restaurant = get_or_create_restaurant(db, current_user)
    from ai.workflows import get_run
    run = _safe_run("workflow_engine", restaurant.id, get_run, db, run_id)
    # Tenant guard: never expose another restaurant's run.
    if run.get("available") and _workflow_belongs(db, run_id, restaurant.id) is False:
        return {"available": False, "error": "Workflow run not found."}
    return run


@router.post("/workflows/{run_id}/resume")
async def ai_workflow_resume(
    run_id: int,
    body: schemas.WorkflowResumeBody = schemas.WorkflowResumeBody(),
    current_user: models.User = Depends(require_role(models.Role.ADMIN)),
    db: Session = Depends(get_db),
):
    """
    Resume a paused run. Body: {"decision": "approve"|"reject", "payload": {...}}.
    An approval advances the run; a rejection cancels it. This is the
    human-in-the-loop hop that gates any mutating step (e.g. creating a real PO).
    """
    restaurant = get_or_create_restaurant(db, current_user)
    if _workflow_belongs(db, run_id, restaurant.id) is False:
        return {"available": False, "error": "Workflow run not found."}
    from ai.workflows import resume
    return _safe_run("workflow_engine", restaurant.id, resume, db, run_id, body.decision, body.payload,
                     current_user.email)


@router.post("/workflows/{run_id}/cancel")
async def ai_workflow_cancel(
    run_id: int,
    current_user: models.User = Depends(require_role(models.Role.ADMIN)),
    db: Session = Depends(get_db),
):
    """Cancel a running/awaiting workflow."""
    restaurant = get_or_create_restaurant(db, current_user)
    if _workflow_belongs(db, run_id, restaurant.id) is False:
        return {"available": False, "error": "Workflow run not found."}
    from ai.workflows import cancel
    return _safe_run("workflow_engine", restaurant.id, cancel, db, run_id)


def _workflow_belongs(db: Session, run_id: int, restaurant_id: int) -> bool:
    """Cross-tenant guard for workflow runs — a run is only visible to its own
    restaurant. Returns False when the run exists but belongs to someone else."""
    row = (
        db.query(models.WorkflowRun.restaurant_id)
        .filter(models.WorkflowRun.id == run_id)
        .first()
    )
    if row is None:
        return True   # non-existent: let the handler return its own not-found
    return row[0] == restaurant_id


# ─────────────────────────────────────────────────────────────────────────────
# KNOWLEDGE GRAPH — cross-domain impact traversal (Phase 6)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/graph/impact")
async def ai_graph_impact(
    entity: str,
    id: int,
    current_user: models.User = Depends(require_staff_role(*_AI_READ)),
    db: Session = Depends(get_db),
):
    """
    Downstream impact of one entity across the Business Knowledge Graph:
    "if this supplier/ingredient/dish changes, what does it affect?" Deterministic
    traversal over the existing tables — suppliers → ingredients → dishes →
    categories — with 30-day revenue-at-risk on the critical dependencies.

    entity: "supplier" | "ingredient" | "menu_item"
    """
    valid = {"supplier", "ingredient", "menu_item"}
    if entity not in valid:
        return {"available": False, "error": f"entity must be one of {sorted(valid)}."}

    restaurant = get_or_create_restaurant(db, current_user)
    from ai.graph import get_impact
    return _safe_run("knowledge_graph", restaurant.id, get_impact, db, restaurant.id, entity, id)


# ─────────────────────────────────────────────────────────────────────────────
# SIMULATION — deterministic "what if…" projection (Phase 2)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/simulate")
async def ai_simulate(
    body: schemas.SimulateBody,
    current_user: models.User = Depends(require_role(models.Role.ADMIN)),
    db: Session = Depends(get_db),
):
    """
    Project the effect of a proposed change before making it: price change,
    promo discount, or supplier cost change. Deterministic — no LLM. Returns
    projected sales/profit/margin deltas, a confidence score, and a
    YES/CAUTION/NO verdict.

    Body: {"change": {"type": "price_change"|"promo"|"cost_change", "item_id": N, ...}}
    See ai/simulation.run_simulation for the accepted change shapes.
    """
    import feature_flags
    if not feature_flags.is_enabled("simulation"):
        return {"available": False, "error": "Simulation is disabled."}

    restaurant = get_or_create_restaurant(db, current_user)
    change = body.change

    from ai.simulation import run_simulation
    return _safe_run("simulation", restaurant.id, run_simulation, db, restaurant.id, change)


@router.get("/forecast/twin")
async def ai_forecast_twin(
    horizon: int = 30,
    current_user: models.User = Depends(require_staff_role(*_AI_READ)),
    db: Session = Depends(get_db),
):
    """
    Digital Twin revenue projection: the restaurant's own sales-history baseline
    combined with exogenous calendar signals (public holidays, school breaks;
    weather/sports once configured). Deterministic. Returns baseline vs projected
    vs uplift, a confidence band, and the days whose projection a signal moved.
    """
    import feature_flags
    if not feature_flags.is_enabled("simulation"):
        return {"available": False, "error": "Simulation is disabled."}

    restaurant = get_or_create_restaurant(db, current_user)
    from ai.simulation import forecast_twin
    return _safe_run("digital_twin", restaurant.id, forecast_twin, db, restaurant.id, horizon)


# ─────────────────────────────────────────────────────────────────────────────
# LABOR INTELLIGENCE
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/labor")
async def ai_labor(
    current_user: models.User = Depends(require_staff_role(*_AI_READ)),
    db: Session = Depends(get_db),
):
    """Labor cost analytics, overtime analysis, and staffing recommendations."""
    restaurant = get_or_create_restaurant(db, current_user)

    from ai.labor.intelligence import get_labor_intelligence
    return await run_in_threadpool(_safe_run, "labor_intelligence", restaurant.id, get_labor_intelligence, db, restaurant.id)


# ─────────────────────────────────────────────────────────────────────────────
# INVENTORY PREDICTIONS
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/inventory")
async def ai_inventory(
    current_user: models.User = Depends(require_staff_role(*_AI_READ)),
    db: Session = Depends(get_db),
):
    """Inventory health, usage velocity, ABC classification, restock predictions."""
    restaurant = get_or_create_restaurant(db, current_user)

    # Bug found 2026-07-07 testing against real production data: this used
    # to import a function name (get_inventory_intelligence) that doesn't
    # exist — the real name is get_inventory_predictions. _safe_run() only
    # catches exceptions from calling the function, not from resolving the
    # import itself, so this was a hard 500 (ImportError), not a graceful
    # {"error": ...} response — nothing had ever exercised this route with a
    # real request before to catch it.
    from ai.inventory_predictor import get_inventory_predictions
    return await run_in_threadpool(_safe_run, "inventory_predictor", restaurant.id, get_inventory_predictions, db, restaurant.id)


# ─────────────────────────────────────────────────────────────────────────────
# PROFIT INTELLIGENCE
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/profit")
async def ai_profit(
    narrate: bool = True,
    current_user: models.User = Depends(require_staff_role(*_AI_READ)),
    db: Session = Depends(get_db),
):
    """
    Contribution margins, profit leaks, portion drift, daypart/channel profitability.

    The numbers are computed deterministically. When an LLM provider is configured
    (and narrate=true), a reasoning layer adds a `narrative` block — plain-language
    judgment over those numbers. It never computes: pass narrate=false to skip the
    LLM call entirely. Absence of `narrative` never means the data failed — it just
    means no provider is set or narration was skipped.
    """
    restaurant = get_or_create_restaurant(db, current_user)

    from ai.profit.intelligence import get_profit_intelligence
    data = await run_in_threadpool(_safe_run, "profit_intelligence", restaurant.id, get_profit_intelligence, db, restaurant.id)

    # Offload the blocking LLM narration off the event loop — see /ai/pricing.
    from ai.reasoning import attach_narrative
    data = await run_in_threadpool(attach_narrative, data, "profit", restaurant.id, narrate)

    return data


# ─────────────────────────────────────────────────────────────────────────────
# ROI — TIME & MONEY SAVED
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/roi")
async def ai_roi(
    narrate: bool = True,
    current_user: models.User = Depends(require_staff_role(*_AI_READ)),
    db: Session = Depends(get_db),
):
    """
    Hours of staff time automated away (converted to money via this
    restaurant's own staff wages), extra profit already captured via approved
    pricing recommendations, and opportunities the AI has flagged but the
    owner hasn't acted on yet. The three totals are kept separate — see
    ai/roi/savings.py's docstring for why they must never be summed.
    """
    restaurant = get_or_create_restaurant(db, current_user)

    from ai.roi.savings import get_roi_savings
    data = await run_in_threadpool(_safe_run, "roi_savings", restaurant.id, get_roi_savings, db, restaurant.id)

    from ai.reasoning import attach_narrative
    data = await run_in_threadpool(attach_narrative, data, "roi", restaurant.id, narrate)

    return data


# ─────────────────────────────────────────────────────────────────────────────
# MARKETING / CAMPAIGNS  (read-only intelligence + owner-approved sends)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/marketing")
async def ai_marketing(
    narrate: bool = True,
    current_user: models.User = Depends(require_staff_role(*_MARKETING_WRITE)),
    db: Session = Depends(get_db),
):
    """
    Read-only marketing view: lapsed regulars to win back, the reachable
    (consented, non-opted-out) audience, recent campaign history, and a list of
    AI-suggested offers each with a plain-language WHY. Nothing is sent here —
    see the POST routes below, which the owner triggers explicitly.
    """
    restaurant = get_or_create_restaurant(db, current_user)

    from ai.marketing import get_marketing_insights
    data = await run_in_threadpool(_safe_run, "marketing", restaurant.id, get_marketing_insights, db, restaurant.id)

    from ai.reasoning import attach_narrative
    data = await run_in_threadpool(attach_narrative, data, "marketing", restaurant.id, narrate)

    return data


def _background_send(fn, *args) -> None:
    """
    Run a (slow, throttled) send loop on its own thread with its own DB session,
    so the request returns immediately. The send functions are opt-out- and
    consent-gated internally; this only handles the threading + session lifecycle.
    """
    import threading

    def _run():
        from database import SessionLocal
        bg = SessionLocal()
        try:
            fn(bg, *args)
        except Exception as exc:  # background thread — never surfaces to a caller
            logger.warning(f"Background send failed: {exc}")
        finally:
            bg.close()

    threading.Thread(target=_run, daemon=True).start()


@router.post("/marketing/promo")
async def ai_marketing_promo(
    body: schemas.MarketingPromoBody,
    current_user: models.User = Depends(require_staff_role(*_MARKETING_WRITE)),
    db: Session = Depends(get_db),
):
    """
    Send a one-off promo to consented, non-opted-out customers who ordered
    recently. Owner-triggered and explicit — the same safe path as the WhatsApp
    `PROMO <offer>` command. Returns the audience it will reach; the send runs in
    the background.
    """
    restaurant = get_or_create_restaurant(db, current_user)
    offer_text = body.offer_text.strip()
    if not offer_text:
        return {"started": False, "audience": 0, "error": "Add an offer to send (e.g. '15% off all mains till 9pm')."}

    from ai.whatsapp import brain
    audience = brain.promo_audience_count(db, restaurant.id)
    if audience == 0:
        return {
            "started": False,
            "audience": 0,
            "error": "No one to send to yet — a promo only reaches diners who gave consent at checkout and haven't opted out.",
        }

    _background_send(brain.broadcast_promo, restaurant.id, offer_text)
    capped = min(audience, brain.PROMO_MAX_RECIPIENTS)
    return {"started": True, "audience": capped, "message": f"Sending your promo to {capped} customer(s). Opted-out customers are skipped automatically."}


@router.post("/marketing/winback")
async def ai_marketing_winback(
    current_user: models.User = Depends(require_staff_role(*_MARKETING_WRITE)),
    db: Session = Depends(get_db),
):
    """
    Send the personalised win-back message to lapsed regulars who gave marketing
    consent and haven't opted out. Owner-triggered and explicit. Returns the
    reachable audience; the send runs in the background and logs
    message_type="campaign_winback".
    """
    restaurant = get_or_create_restaurant(db, current_user)

    from ai.whatsapp import brain
    reachable = brain.winback_reachable(db, restaurant.id)
    if reachable == 0:
        return {
            "started": False,
            "audience": 0,
            "error": "No reachable lapsed regulars — a win-back only reaches customers who gave consent and haven't opted out.",
        }

    _background_send(brain.broadcast_winback, restaurant.id)
    capped = min(reachable, brain.PROMO_MAX_RECIPIENTS)
    return {"started": True, "audience": capped, "message": f"Sending win-back messages to {capped} lapsed regular(s). Opted-out customers are skipped automatically."}


# ─────────────────────────────────────────────────────────────────────────────
# EXPLAIN THIS  (on-demand plain-language explanation of one insight)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/explain")
async def ai_explain(
    body: schemas.ExplainBody,
    current_user: models.User = Depends(require_staff_role(*_AI_READ)),
    db: Session = Depends(get_db),
):
    """
    Explain a SINGLE insight (a pricing rec, profit leak, menu item, …) in plain
    language for a non-analyst owner. Reuses the grounded reasoning layer at the
    cheap tier — every figure it cites is checked against the item passed in.
    Body: {"item": {...}, "label": "optional context"}. Returns {available, explanation}.
    """
    restaurant = get_or_create_restaurant(db, current_user)
    if not isinstance(body.item, dict):
        return {"available": False, "error": "Provide an 'item' object to explain."}

    payload = {"item": body.item, "context": body.label}

    from starlette.concurrency import run_in_threadpool
    from ai.reasoning import narrate
    note = await run_in_threadpool(narrate, payload, "explain", restaurant_id=restaurant.id)
    if not note:
        return {"available": False}
    return {"available": True, "explanation": note}


# ─────────────────────────────────────────────────────────────────────────────
# COST-PRICE DATA QUALITY
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/data-quality")
async def ai_data_quality(
    current_user: models.User = Depends(require_staff_role(*_AI_READ)),
    db: Session = Depends(get_db),
):
    """
    Flags menu items with missing or implausible cost prices. Every profit and
    pricing figure depends on cost_price, so this is the data-integrity guard for
    all of them — deterministic, no LLM.
    """
    restaurant = get_or_create_restaurant(db, current_user)

    from ai.data_quality import get_cost_price_quality
    return await run_in_threadpool(_safe_run, "data_quality", restaurant.id, get_cost_price_quality, db, restaurant.id)


# ─────────────────────────────────────────────────────────────────────────────
# SUPPLY CHAIN INTELLIGENCE
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/supply-chain")
async def ai_supply_chain(
    current_user: models.User = Depends(require_staff_role(*_AI_READ)),
    db: Session = Depends(get_db),
):
    """Supplier performance analysis, overdue purchase orders, reorder recommendations."""
    restaurant = get_or_create_restaurant(db, current_user)

    from ai.supply_chain.intelligence import get_supply_chain_intelligence
    return await run_in_threadpool(_safe_run, "supply_chain_intelligence", restaurant.id, get_supply_chain_intelligence, db, restaurant.id)


# ─────────────────────────────────────────────────────────────────────────────
# AI OPS — token spend, agent latency/reliability, grounding (surfaces metered data)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/usage")
async def ai_usage(
    days: int = 30,
    current_user: models.User = Depends(require_staff_role(*_AI_READ)),
    db: Session = Depends(get_db),
):
    """
    AIOps summary for this tenant: LLM token spend (by model), per-agent latency
    (p50/p95) + success rate, and the grounding trust rate. Read-only aggregation
    of already-metered data (token_usage, agent_executions, grounding verifier).

    Gated to Owner (Role.ADMIN bypass) + Manager/Controller (directive 015's
    `ai-ops` matrix row: RW Owner, R Manager/Controller) — this is
    management/cost intelligence, not something a floor-staff (Waiter/Kitchen/
    Stockkeeper) account needs.
    """
    restaurant = get_or_create_restaurant(db, current_user)
    days = min(max(days, 1), 365)
    from ai.evaluation.tracker import get_ai_ops_summary
    return _safe_run("ai_ops_summary", restaurant.id, get_ai_ops_summary, db, restaurant.id, days)
