"""
backend/ai/spend_guard.py
───────────────────────────
Per-tenant AI/LLM spend cap (tech-debt D14). Before this, /ai/* and
/analytics/* metered token spend to TokenUsage but never blocked on it — a
runaway loop or a shared/compromised admin credential could run unbounded
LLM spend with nothing but after-the-fact visibility (GET /ai/usage).

Deliberately DB-backed, not an in-process counter: backend/rate_limit.py
documents that this repo runs a single Gunicorn worker specifically to keep
its in-memory rate limiter correct until Redis is provisioned. A spend cap
has to survive restarts and stay correct regardless of worker count, so it
reads the same TokenUsage table /ai/usage already aggregates (indexed via
ix_token_usage_restaurant_created), converting cost the same way
cost_model.py already does — no second pricing table to drift out of sync.
"""

from __future__ import annotations

import os

from sqlalchemy.orm import Session

from ai.cost_model import cost_usd
from time_utils import utcnow

# Env-tunable, same style as cost_model.py. Defaults are conservative starting
# points for a single-tenant pilot, not a considered business number — an
# operator should override via env once real usage patterns are known.
DAILY_CAP_USD = float(os.getenv("AI_DAILY_SPEND_CAP_USD", "5.0"))
MONTHLY_CAP_USD = float(os.getenv("AI_MONTHLY_SPEND_CAP_USD", "60.0"))
WARN_RATIO = float(os.getenv("AI_SPEND_WARN_RATIO", "0.8"))


def _spend_since(db: Session, restaurant_id: int, since) -> float:
    import models

    rows = (
        db.query(models.TokenUsage.llm_model, models.TokenUsage.input_tokens, models.TokenUsage.output_tokens)
        .filter(models.TokenUsage.restaurant_id == restaurant_id, models.TokenUsage.created_at >= since)
        .all()
    )
    return sum(cost_usd(model, inp or 0, out or 0) for model, inp, out in rows)


def get_budget_status(restaurant_id: int, db: Session | None = None) -> dict:
    """
    Today's and this month's AI spend for `restaurant_id` against the
    configured caps. Opens its own short-lived session when `db` isn't given
    (mirrors ai/reasoning/narrator.py::_log_usage) so a caller deep in a
    request that doesn't already have a Session handy — like narrate() —
    doesn't need to thread one through.
    """
    own_session = db is None
    if own_session:
        from database import SessionLocal
        db = SessionLocal()
    try:
        now = utcnow()
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = day_start.replace(day=1)

        daily_spend = _spend_since(db, restaurant_id, day_start)
        monthly_spend = _spend_since(db, restaurant_id, month_start)

        blocked = daily_spend >= DAILY_CAP_USD or monthly_spend >= MONTHLY_CAP_USD
        warn = (
            not blocked
            and (daily_spend >= DAILY_CAP_USD * WARN_RATIO or monthly_spend >= MONTHLY_CAP_USD * WARN_RATIO)
        )

        return {
            "daily_spend_usd": round(daily_spend, 4),
            "daily_cap_usd": DAILY_CAP_USD,
            "daily_remaining_usd": round(max(0.0, DAILY_CAP_USD - daily_spend), 4),
            "monthly_spend_usd": round(monthly_spend, 4),
            "monthly_cap_usd": MONTHLY_CAP_USD,
            "monthly_remaining_usd": round(max(0.0, MONTHLY_CAP_USD - monthly_spend), 4),
            "warn": warn,
            "blocked": blocked,
        }
    finally:
        if own_session:
            db.close()
