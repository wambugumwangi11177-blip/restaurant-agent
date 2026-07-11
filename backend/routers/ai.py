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

from database import get_db
from auth import get_current_user
import models
from routers.deps import get_or_create_restaurant

logger = logging.getLogger("ai.router")

router = APIRouter(prefix="/ai", tags=["ai"])


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
    current_user: models.User = Depends(get_current_user),
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

    from ai.pricing.recommendations import get_pricing_intelligence
    data = _safe_run("pricing_intelligence", restaurant.id, get_pricing_intelligence, db, restaurant.id)

    # narrate() drives a synchronous, blocking LLM SDK call. This route is async,
    # so run it off the event loop or the whole worker stalls for the round-trip.
    from starlette.concurrency import run_in_threadpool
    from ai.reasoning import attach_narrative
    data = await run_in_threadpool(attach_narrative, data, "pricing", restaurant.id, narrate)

    return data


@router.post("/pricing/{rec_id}/approve")
async def approve_pricing_rec(
    rec_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Approve a pricing recommendation — updates menu item price immediately."""
    restaurant = get_or_create_restaurant(db, current_user)
    from ai.pricing.recommendations import approve_recommendation
    return approve_recommendation(db, rec_id, restaurant.id, approved_by=current_user.email)


@router.post("/pricing/{rec_id}/reject")
async def reject_pricing_rec(
    rec_id: int,
    body: dict = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Reject a pricing recommendation."""
    restaurant = get_or_create_restaurant(db, current_user)
    from ai.pricing.recommendations import reject_recommendation
    reason = (body or {}).get("reason", "")
    return reject_recommendation(db, rec_id, restaurant.id, reason)


# ─────────────────────────────────────────────────────────────────────────────
# LABOR INTELLIGENCE
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/labor")
async def ai_labor(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Labor cost analytics, overtime analysis, and staffing recommendations."""
    restaurant = get_or_create_restaurant(db, current_user)

    from ai.labor.intelligence import get_labor_intelligence
    return _safe_run("labor_intelligence", restaurant.id, get_labor_intelligence, db, restaurant.id)


# ─────────────────────────────────────────────────────────────────────────────
# INVENTORY PREDICTIONS
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/inventory")
async def ai_inventory(
    current_user: models.User = Depends(get_current_user),
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
    return _safe_run("inventory_predictor", restaurant.id, get_inventory_predictions, db, restaurant.id)


# ─────────────────────────────────────────────────────────────────────────────
# PROFIT INTELLIGENCE
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/profit")
async def ai_profit(
    narrate: bool = True,
    current_user: models.User = Depends(get_current_user),
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
    data = _safe_run("profit_intelligence", restaurant.id, get_profit_intelligence, db, restaurant.id)

    # Offload the blocking LLM narration off the event loop — see /ai/pricing.
    from starlette.concurrency import run_in_threadpool
    from ai.reasoning import attach_narrative
    data = await run_in_threadpool(attach_narrative, data, "profit", restaurant.id, narrate)

    return data


# ─────────────────────────────────────────────────────────────────────────────
# ROI — TIME & MONEY SAVED
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/roi")
async def ai_roi(
    narrate: bool = True,
    current_user: models.User = Depends(get_current_user),
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
    data = _safe_run("roi_savings", restaurant.id, get_roi_savings, db, restaurant.id)

    from starlette.concurrency import run_in_threadpool
    from ai.reasoning import attach_narrative
    data = await run_in_threadpool(attach_narrative, data, "roi", restaurant.id, narrate)

    return data


# ─────────────────────────────────────────────────────────────────────────────
# MARKETING / CAMPAIGNS  (read-only intelligence + owner-approved sends)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/marketing")
async def ai_marketing(
    narrate: bool = True,
    current_user: models.User = Depends(get_current_user),
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
    data = _safe_run("marketing", restaurant.id, get_marketing_insights, db, restaurant.id)

    from starlette.concurrency import run_in_threadpool
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
    body: dict,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Send a one-off promo to consented, non-opted-out customers who ordered
    recently. Owner-triggered and explicit — the same safe path as the WhatsApp
    `PROMO <offer>` command. Returns the audience it will reach; the send runs in
    the background.
    """
    restaurant = get_or_create_restaurant(db, current_user)
    offer_text = (body or {}).get("offer_text", "").strip()
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
    current_user: models.User = Depends(get_current_user),
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
    body: dict,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Explain a SINGLE insight (a pricing rec, profit leak, menu item, …) in plain
    language for a non-analyst owner. Reuses the grounded reasoning layer at the
    cheap tier — every figure it cites is checked against the item passed in.
    Body: {"item": {...}, "label": "optional context"}. Returns {available, explanation}.
    """
    restaurant = get_or_create_restaurant(db, current_user)
    item = body.get("item")
    if not isinstance(item, dict):
        return {"available": False, "error": "Provide an 'item' object to explain."}

    payload = {"item": item, "context": body.get("label", "")}

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
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Flags menu items with missing or implausible cost prices. Every profit and
    pricing figure depends on cost_price, so this is the data-integrity guard for
    all of them — deterministic, no LLM.
    """
    restaurant = get_or_create_restaurant(db, current_user)

    from ai.data_quality import get_cost_price_quality
    return _safe_run("data_quality", restaurant.id, get_cost_price_quality, db, restaurant.id)


# ─────────────────────────────────────────────────────────────────────────────
# SUPPLY CHAIN INTELLIGENCE
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/supply-chain")
async def ai_supply_chain(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Supplier performance analysis, overdue purchase orders, reorder recommendations."""
    restaurant = get_or_create_restaurant(db, current_user)

    from ai.supply_chain.intelligence import get_supply_chain_intelligence
    return _safe_run("supply_chain_intelligence", restaurant.id, get_supply_chain_intelligence, db, restaurant.id)


# ─────────────────────────────────────────────────────────────────────────────
# AI OPS — token spend, agent latency/reliability, grounding (surfaces metered data)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/usage")
async def ai_usage(
    days: int = 30,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    AIOps summary for this tenant: LLM token spend (by model), per-agent latency
    (p50/p95) + success rate, and the grounding trust rate. Read-only aggregation
    of already-metered data (token_usage, agent_executions, grounding verifier).

    Scoped to the caller's own restaurant, so any authenticated owner/staff can
    see what their AI costs and how well it's working — the counterweight to the
    ROI page's "what it saves." (Previously ADMIN-only, which hid it from owners,
    who register as STAFF by default and so could never see their own usage.)
    """
    restaurant = get_or_create_restaurant(db, current_user)
    days = min(max(days, 1), 365)
    from ai.evaluation.tracker import get_ai_ops_summary
    return _safe_run("ai_ops_summary", restaurant.id, get_ai_ops_summary, db, restaurant.id, days)
