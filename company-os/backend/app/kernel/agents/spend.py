"""
app/kernel/agents/spend.py
──────────────────────────
Daily LLM spend circuit-breaker per workspace (ported from restaurant-agent's
ai/spend_cap.py). A runaway loop or an abusive caller stops at the cap instead
of running up a bill. Resets at 00:00 UTC.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.kernel.models import AgentRun


def start_of_utc_day() -> datetime:
    return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


def today_spend_usd(db: Session, workspace_id: int) -> Decimal:
    total = db.execute(
        select(func.coalesce(func.sum(AgentRun.cost_usd), 0)).where(
            AgentRun.workspace_id == workspace_id, AgentRun.created_at >= start_of_utc_day()
        )
    ).scalar_one()
    return Decimal(total)


def cap_usd() -> Decimal:
    return Decimal(str(get_settings().daily_llm_spend_cap_usd))


def over_cap(db: Session, workspace_id: int, pending: Decimal = Decimal("0")) -> bool:
    return today_spend_usd(db, workspace_id) + pending >= cap_usd()
