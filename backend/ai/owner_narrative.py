"""Bounded, scrubbed and metered optional narration for owner chat/reports.

Only text leaves this boundary. No tools or operational write capabilities are
provided. Numeric verification remains the caller's job; it is not a complete
semantic or prompt-injection defense.
"""
import logging
import re

from fastapi import HTTPException

import models
from ai import llm_client, pii_scrub, spend_cap
from ai.cost_model import cost_usd

logger = logging.getLogger(__name__)


def _drop_reservation(db, reservation_id):
    """The provider call failed, so nothing was spent: give the reserved estimate back."""
    try:
        db.rollback()
        row = db.get(models.TokenUsage, reservation_id)
        if row is not None:
            db.delete(row)
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("narrate: could not release a reserved estimate; it stays counted until midnight UTC", exc_info=True)


def _record_actual_usage(db, reservation_id, restaurant_id, prompt_version, result):
    """Replace the reserved estimate with what the provider reported. Paid output is metered even if a later
    grounding check rejects its content. If this write fails the estimate stays, so spend is over-counted,
    never lost."""
    try:
        row = db.get(models.TokenUsage, reservation_id)
        if row is None:
            row = models.TokenUsage(restaurant_id=restaurant_id, prompt_version=prompt_version)
            db.add(row)
        row.llm_model = result.model
        row.input_tokens = result.usage.input_tokens
        row.output_tokens = result.usage.output_tokens
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("narrate: could not record actual token usage; the reserved estimate stays", exc_info=True)


def narrate(db, user, restaurant_id, messages, system, max_tokens, prompt_version,
            temperature=0.0, tier="medium", extra_body=None):
    """One scrubbed, budget-checked, metered provider call.

    `temperature`/`tier` default to the deterministic-narration settings every
    existing caller relies on (0 / medium). The creative layer (ai/creative.py)
    passes its own; the budget estimate below uses the SAME tier as the call so a
    dearer creative model cannot slip past the cap on a medium-model estimate.

    The budget is checked and this call's estimated cost is reserved (as a usage row) in one short
    transaction under a tenant lock. That transaction is committed BEFORE the provider is called, so a slow
    model never holds a database lock or connection, and a simultaneous request already sees this call's
    reservation when it checks the budget. When the provider answers, the reservation is replaced by the
    real usage; when it fails, the reservation is removed.
    """
    # Lock the tenant while checking and reserving so simultaneous chat/report
    # requests cannot independently spend the same remaining estimated budget.
    db.query(models.Tenant).filter_by(id=user.tenant_id).with_for_update().one()
    restaurant_ids = [row[0] for row in db.query(models.Restaurant.id).filter_by(tenant_id=user.tenant_id)]
    if restaurant_id not in restaurant_ids:
        raise HTTPException(404, "Restaurant not found")
    spent = sum(spend_cap.today_spend_usd(db, rid) for rid in restaurant_ids)
    known_names = pii_scrub.known_names_for_restaurant(db, restaurant_id)
    clean_system = pii_scrub.scrub_for_llm(system, known_names)
    clean_messages = [{"role": m["role"], "content": pii_scrub.scrub_for_llm(m["content"], known_names)} for m in messages]
    # UTF-8 bytes overestimate ordinary text tokens. Include a framing margin.
    input_bound = len(clean_system.encode()) + sum(len(m['content'].encode()) for m in clean_messages) + 1024
    model = llm_client.model_for_tier(tier)
    estimate = cost_usd(model, input_bound, max_tokens)
    if extra_body:
        estimate += 0.01  # a provider-side web search is billed per request, on top of tokens
    if spent + estimate >= spend_cap.DAILY_LLM_SPEND_CAP_USD:
        raise HTTPException(429, "Daily estimated AI budget reached. Deterministic reports remain available.")
    # Reserve the estimate as a usage row, then commit to release the tenant lock before the slow call. (The
    # optional web-search surcharge is checked above but not stored: usage rows hold tokens only.)
    reservation = models.TokenUsage(restaurant_id=restaurant_id, llm_model=model, prompt_version=prompt_version,
                                    input_tokens=input_bound, output_tokens=max_tokens)
    db.add(reservation)
    db.flush()
    reservation_id = reservation.id
    db.commit()
    extra = {"extra_body": extra_body} if extra_body else {}
    try:
        result = llm_client.chat_with_usage(clean_messages, system=clean_system,
                                            max_tokens=max_tokens, tier=tier, temperature=temperature, **extra)
    except Exception:
        _drop_reservation(db, reservation_id)
        raise
    _record_actual_usage(db, reservation_id, restaurant_id, prompt_version, result)
    return pii_scrub.scrub_for_llm(result.text, known_names)


# ── Reasoning-leak stripping ─────────────────────────────────────────────────
# Shared by the report narrative and the creative layer: small reasoning models
# sometimes emit their planning before (or instead of) the finished text.

_LEAK_STARTERS = re.compile(
    r"^(we need|let me|i need|i'll|i will|to (produce|draft|write)|first|okay|sure|here's a plan|thinking|must have|should i|note:)",
    re.IGNORECASE,
)
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)
_THINK_UNTERMINATED = re.compile(r"<think>.*\Z", re.IGNORECASE | re.DOTALL)


def _strip_think_blocks(text: str) -> str:
    text = text or ""
    if "</think>" in text.lower() and "<think>" not in text.lower():
        text = re.split(r"</think>", text, flags=re.IGNORECASE)[-1]
    text = _THINK_BLOCK.sub("", text)
    return _THINK_UNTERMINATED.sub("", text)


def strip_reasoning_leak(text: str) -> str:
    """nemotron-style reasoning models sometimes prepend their planning
    ('We need to produce a daily report...'). Strip any leading lines that
    are meta-commentary so the owner only sees the finished report. A line is
    meta if it starts with a leak-starter AND the following content restarts
    with a proper report line — simplest robust rule: drop leading lines that
    match leak starters or mention 'report for'/'numbers exactly' style task
    echo, until the first line that reads like report prose.

    Also removes <think>…</think> blocks: closed ones anywhere, an unterminated
    one (output cut off mid-thought) to the end, and a lone closing tag's
    preceding reasoning."""
    text = _strip_think_blocks(text)
    lines = text.strip().splitlines()
    out: list[str] = []
    started = False
    for line in lines:
        stripped = line.strip()
        if not started and stripped and (
            _LEAK_STARTERS.match(stripped)
            or "report for" in stripped.lower()
            or "numbers exactly" in stripped.lower()
            or "we'll" in stripped.lower()
            or "we need to" in stripped.lower()
            or (stripped.endswith(":") and len(stripped) < 80)
        ):
            continue
        if stripped:
            started = True
        out.append(line)
    return "\n".join(out).strip() or text.strip()


# Creative prose (ai/creative.py) is warm and conversational, so the report
# filter's broad rules above would eat real sentences: a first paragraph that
# says "we'll" or "the report for this week", or opens with "First," / "Sure,",
# or a short "My read:" header line, is exactly what that voice produces. Only
# unmistakable planning openers are removed here.
_CREATIVE_LEAK_STARTERS = re.compile(
    r"^(we need to|i need to|let me (think|plan|draft|write|figure)\b|okay,? so\b|so the user\b"
    r"|the user (wants|asked|is asking)\b|the task is\b|here's a plan\b"
    r"|to (produce|draft|write) (the|a|this)\b|(thinking|plan|draft|note)\s*:)",
    re.IGNORECASE,
)


def strip_creative_leak(text: str) -> str:
    """Remove leaked reasoning from creative text without touching its voice.

    Strips <think> blocks like strip_reasoning_leak, then only leading lines that
    open with an explicit planning phrase. Unlike the report filter it never falls
    back to the raw text: if nothing but planning is left, nothing is shown."""
    lines = _strip_think_blocks(text).strip().splitlines()
    out: list[str] = []
    started = False
    for line in lines:
        stripped = line.strip()
        if not started and stripped and _CREATIVE_LEAK_STARTERS.match(stripped):
            continue
        if stripped:
            started = True
        out.append(line)
    return "\n".join(out).strip()
