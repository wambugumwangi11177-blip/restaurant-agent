"""
backend/ai/spend_cap.py
─────────────────────────
Daily LLM spend circuit-breaker (audit remediation, Tier 3 item 7).

`GET /ai/usage` already surfaced token spend as read-only telemetry, but nothing
stopped a call once spend crossed any threshold — the LLM-calling routes in
routers/ai.py had no rate limit and no cost ceiling at all. This adds the missing
half: a per-tenant, per-day cap enforced as a FastAPI dependency, reusing
TokenUsage (already indexed on (restaurant_id, created_at) — see models.py) and
cost_model.cost_usd (already converts tokens to dollars). No new table.

Applied only to the routes that actually call attach_narrative/narrate — see
routers/ai.py's `_LLM_TOUCHING` set — not the purely deterministic ones.
"""

from __future__ import annotations

import logging
import os

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import models
from ai.cost_model import cost_usd
from routers.deps import get_or_create_restaurant
from time_utils import utcnow

logger = logging.getLogger(__name__)

# Generous default — this is a circuit breaker against a runaway loop or abuse,
# not a tight budget knob; tune per-deployment via env.
_DEFAULT_DAILY_CAP = "20.0"


def _parse_spend_cap() -> float:
    """Parse DAILY_LLM_SPEND_CAP_USD from the environment, falling back to the
    default and logging a warning if the value is invalid."""
    raw = os.getenv("DAILY_LLM_SPEND_CAP_USD", _DEFAULT_DAILY_CAP)
    try:
        value = float(raw)
    except (ValueError, TypeError):
        logger.warning(
            "DAILY_LLM_SPEND_CAP_USD=%r is not a valid float; "
            "falling back to default %s",
            raw,
            _DEFAULT_DAILY_CAP,
        )
        value = float(_DEFAULT_DAILY_CAP)
    return value


DAILY_LLM_SPEND_CAP_USD: float = _parse_spend_cap()


def today_spend_usd(db: Session, restaurant_id: int) -> float:
    """Sum of cost_usd() over this restaurant's TokenUsage rows created today
    (UTC, naive — matching every other cutoff comparison in this codebase, see
    time_utils.py). Uses the existing ix_token_usage_restaurant_created index."""
    start_of_today = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    rows = (
        db.query(models.TokenUsage.llm_model, models.TokenUsage.input_tokens, models.TokenUsage.output_tokens)
        .filter(
            models.TokenUsage.restaurant_id == restaurant_id,
            models.TokenUsage.created_at >= start_of_today,
        )
        .all()
    )
    total = 0.0
    for model, in_tok, out_tok in rows:
        try:
            total += cost_usd(model, in_tok or 0, out_tok or 0)
        except Exception:
            logger.warning(
                "cost_usd() failed for model=%r in_tok=%r out_tok=%r; skipping row",
                model,
                in_tok,
                out_tok,
                exc_info=True,
            )
    return total


def check_spend_cap(current_user: models.User, db: Session) -> None:
    """
    Call at the top of an LLM-touching route body, after `current_user`/`db` are
    resolved by their own Depends() — not itself a bare Depends(), since it needs
    the restaurant derived from current_user rather than a fresh lookup, to stay
    consistent with the rest of the route.

    Raises 429 once today's spend for this tenant is at or above the cap.
    """
    restaurant = get_or_create_restaurant(db, current_user)
    spent = today_spend_usd(db, restaurant.id)
    if spent >= DAILY_LLM_SPEND_CAP_USD:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Daily AI spend cap reached (${spent:.2f} of ${DAILY_LLM_SPEND_CAP_USD:.2f}). "
                "Resets at midnight UTC, or raise DAILY_LLM_SPEND_CAP_USD."
            ),
        )