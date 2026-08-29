"""
backend/ai/whatsapp/conversation.py
─────────────────────────────────────
Short-term conversation memory for the WhatsApp LLM orchestrator (Phase 6).
Loads the recent owner<->assistant turns for a restaurant so a follow-up message
carries context, and persists new turns. Keyed by restaurant_id (see the
ConversationTurn model for why). Only used when FEATURE_CONVERSATION_MEMORY is on.
"""

import logging
import models

logger = logging.getLogger("ai.conversation")

# How many prior turns to feed back into the model — ~3 exchanges. Small on
# purpose: enough for "and last week?" style follow-ups without ballooning tokens.
MAX_TURNS = 6


def load_recent(db, restaurant_id: int, limit: int = MAX_TURNS) -> list[dict]:
    """Recent turns for this restaurant as [{role, content}, ...], oldest first
    (the order the LLM expects). Read-only; safe on the caller's session."""
    try:
        rows = (
            db.query(models.ConversationTurn)
            .filter(models.ConversationTurn.restaurant_id == restaurant_id)
            .order_by(
                models.ConversationTurn.created_at.desc(),
                models.ConversationTurn.id.desc(),
            )
            .limit(limit)
            .all()
        )
    except Exception as exc:  # table missing / db hiccup — degrade to no memory
        logger.warning("[Conversation] load_recent failed: %s", exc)
        return []
    rows.reverse()
    return [{"role": r.role, "content": r.content} for r in rows]


def save_turn(restaurant_id: int, role: str, content: str) -> None:
    """Persist one turn on its own short-lived session, so conversation logging
    never commits or interferes with the caller's request transaction (same
    pattern as orchestrator._log_usage)."""
    from database import SessionLocal
    session = SessionLocal()
    try:
        session.add(models.ConversationTurn(
            restaurant_id=restaurant_id, role=role, content=content,
        ))
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.warning("[Conversation] save_turn failed: %s", exc)
    finally:
        session.close()