"""
backend/ai/reasoning/narrator.py
──────────────────────────────────
The reasoning layer — turns a deterministic analytics payload into plain-language
judgment (a headline, ranked priorities, and concrete actions).

Hard boundary (the whole reason this project splits deterministic vs. LLM):
  • The LLM NEVER computes. It is handed the numbers the Python modules already
    calculated and is instructed to only cite figures that appear verbatim in
    the payload. It interprets, prioritizes, and recommends — it does not do math.
  • If no LLM provider is configured, narrate() returns None and the caller keeps
    serving the deterministic payload unchanged. The reasoning layer is strictly
    additive; nothing depends on it to function.

Cost discipline (tie-in with ai/llm_client.py's tier system):
  • Each task declares a complexity TIER. Routine single-module narration is LOW
    (cheap/fast model); cross-domain strategy would be MEDIUM/HIGH. A dashboard
    refresh therefore costs a handful of the cheapest calls, not frontier-model
    calls.
  • Results are cached on a hash of (task, tier, payload). Identical numbers →
    identical narrative → zero tokens. Insights only re-narrate when the
    underlying deterministic numbers actually move, which is exactly the
    behaviour we want: the AI "re-thinks" only when there's something new to
    think about.
  • Token usage is logged per-tenant to the token_usage table (same metering the
    Phase 2 orchestrator uses) when a restaurant_id is supplied.
"""

import hashlib
import json
import logging

from ai import llm_client
from ai.llm_client import TIER_LOW, TIER_MEDIUM, TIER_HIGH  # noqa: F401  (re-exported)
from . import grounding

logger = logging.getLogger("ai.reasoning")

# Reasoning runs at temperature 0: we want the most deterministic, least
# embellished reading of the numbers, not creative writing. Lower temperature
# also measurably reduces the rate of invented figures — the first line of
# defence, before the grounding verifier catches whatever still slips through.
_TEMPERATURE = 0.0

# Guard against dumping a huge payload into the prompt — trims tokens/latency.
# The deterministic modules return summary + detail; the salient signal is well
# within this budget, and `keys` whitelists below trim most tasks further.
_MAX_PAYLOAD_CHARS = 12000

# Process-local memo of hash -> narrative. Bounded so a long-running worker
# doesn't grow unboundedly. Not shared across processes (fine — worst case a
# cold worker re-narrates once), and intentionally not persisted: it's a token
# saver, not a source of truth.
_cache: dict[str, dict] = {}
_CACHE_MAX = 256


# ─────────────────────────────────────────────────────────────────────────────
# TASK REGISTRY — one entry per deterministic module we narrate.
# tier  : which model tier this task runs on (cost control lives here).
# role  : who the model is playing.
# focus : what to pay attention to for THIS domain.
# keys  : optional whitelist of top-level payload keys to send (trims tokens);
#         None = send the whole payload.
# ─────────────────────────────────────────────────────────────────────────────
TASKS = {
    "profit": {
        "tier": TIER_LOW,
        "role": "You are a sharp restaurant profit analyst advising the owner.",
        "focus": (
            "Explain in plain language what is making and losing money, and the "
            "highest-leverage fixes. Call out margin leaks, low-margin bestsellers, "
            "and channel/daypart profitability if present."
        ),
        "keys": None,
    },
    "menu": {
        "tier": TIER_LOW,
        "role": "You are a menu engineering consultant advising the owner.",
        "focus": (
            "Interpret the Star/Plowhorse/Puzzle/Dog matrix. Say which items to "
            "promote, reprice, fix, or cut, and why."
        ),
        "keys": ["summary", "recommendations", "category_performance", "pareto"],
    },
    "pricing": {
        "tier": TIER_MEDIUM,  # pricing is a money decision → worth the better model
        "role": "You are a revenue-management strategist advising the owner.",
        "focus": (
            "Turn the SURGE/REPRICE/STIMULATE signals into a clear, ordered plan. "
            "Weigh demand, margin, and customer-perception risk of each change."
        ),
        "keys": None,
    },
}

# Output contract the model must return. Kept tiny and strict so it parses
# reliably even on smaller models.
_OUTPUT_SHAPE = (
    '{"headline": "one-sentence bottom line", '
    '"priorities": ["most important issue first", "..."], '
    '"actions": [{"action": "what to do", "why": "reason citing the data", '
    '"impact": "expected effect"}]}'
)


def narrate(payload: dict, task: str, *, restaurant_id: int | None = None,
            tier: str | None = None) -> dict | None:
    """
    Produce an LLM narrative for a deterministic analytics payload.

    payload       : the dict returned by a deterministic module (e.g. profit).
    task          : a key in TASKS ("profit", "menu", "pricing").
    restaurant_id : if given, token usage is metered to this tenant.
    tier          : override the task's default tier (else TASKS[task]["tier"]).

    Returns a dict {headline, priorities[], actions[], model, tier, cached} or
    None when no provider is configured / the call fails — callers must treat
    None as "no narrative available" and fall back to the raw payload.
    """
    if not isinstance(payload, dict):
        return None
    if not llm_client.is_available():
        return None

    cfg = TASKS.get(task)
    if cfg is None:
        logger.warning("narrate(): no task config for %r", task)
        return None

    tier = tier or cfg["tier"]
    payload_json = _shrink(payload, cfg.get("keys"))
    cache_key = hashlib.sha256(f"{task}|{tier}|{payload_json}".encode("utf-8")).hexdigest()

    cached = _cache.get(cache_key)
    if cached is not None:
        return {**cached, "cached": True}

    system = _build_system(cfg)
    user = (
        "Here is the deterministic analytics data as JSON. Only cite numbers "
        "that appear in it — never invent, round differently, or recompute:\n\n"
        f"{payload_json}"
    )

    try:
        resp = llm_client.chat_with_usage(
            messages=[{"role": "user", "content": user}],
            system=system,
            max_tokens=700,
            tier=tier,
            temperature=_TEMPERATURE,
        )
    except Exception as exc:  # network / provider / bad model id — degrade cleanly
        logger.warning("narrate(): LLM call failed for task=%s tier=%s: %s", task, tier, exc)
        return None

    narrative = _parse(resp.text)
    # Grounding guard: redact any figure the model wrote that isn't backed by the
    # deterministic payload, and record it. verify() adds `verified` +
    # `ungrounded_numbers`. This is what makes the narrative safe to show.
    narrative = grounding.verify(narrative, payload)
    narrative["model"] = resp.model
    narrative["tier"] = tier
    narrative["cached"] = False
    if not narrative["verified"]:
        logger.warning("narrate(): redacted ungrounded numbers %s in task=%s",
                       narrative["ungrounded_numbers"], task)

    if restaurant_id is not None:
        _log_usage(restaurant_id, resp)

    _remember(cache_key, narrative)
    return narrative


# ─────────────────────────────────────────────────────────────────────────────
# INTERNALS
# ─────────────────────────────────────────────────────────────────────────────

def _build_system(cfg: dict) -> str:
    return (
        f"{cfg['role']} {cfg['focus']}\n\n"
        "You are given deterministic analytics as JSON that a separate system "
        "already computed. The app shows the exact figures to the owner "
        "alongside your words, so your job is JUDGEMENT, not reporting numbers. "
        "Rules you must follow:\n"
        "1. Prefer qualitative, directional language — 'your bestseller has a "
        "thin margin', 'delivery is your least profitable channel'. Avoid "
        "quoting specific figures.\n"
        "2. If you do reference a number, it MUST be copied verbatim from the "
        "JSON. NEVER invent, estimate, round, or recompute any figure — that "
        "math is not your job and wrong numbers destroy trust.\n"
        "3. Be concise, specific, and grounded in THIS restaurant's data.\n"
        "4. Respond with ONLY a JSON object, no prose around it, of this exact "
        f"shape:\n{_OUTPUT_SHAPE}"
    )


def _shrink(payload: dict, keys: list[str] | None) -> str:
    """Serialize the payload (optionally whitelisting top-level keys) with a size cap."""
    obj = {k: payload[k] for k in keys if k in payload} if keys else payload
    s = json.dumps(obj, default=str, ensure_ascii=False)
    if len(s) > _MAX_PAYLOAD_CHARS:
        s = s[:_MAX_PAYLOAD_CHARS] + '..."<truncated>"'
    return s


def _parse(text: str) -> dict:
    """
    Parse the model's reply into the output contract. Defensive: smaller models
    sometimes wrap JSON in prose or fences, so we extract the first {...} block.
    On total failure we still return a usable narrative (the raw text as headline)
    rather than erroring — the caller only ever gets a well-formed dict or None.
    """
    text = (text or "").strip()
    candidate = text
    if not candidate.startswith("{"):
        start, end = candidate.find("{"), candidate.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = candidate[start:end + 1]
    try:
        data = json.loads(candidate)
        if isinstance(data, dict):
            return {
                "headline": str(data.get("headline", "")).strip(),
                "priorities": [str(p) for p in data.get("priorities", []) if str(p).strip()],
                "actions": [a for a in data.get("actions", []) if isinstance(a, dict)],
            }
    except (json.JSONDecodeError, ValueError):
        pass
    return {"headline": text[:280], "priorities": [], "actions": [], "parse_fallback": True}


def _remember(key: str, value: dict) -> None:
    if len(_cache) >= _CACHE_MAX:
        _cache.pop(next(iter(_cache)))  # evict oldest (dicts preserve insertion order)
    _cache[key] = value


def _log_usage(restaurant_id: int, resp) -> None:
    """Meter one reasoning call to token_usage. Own short-lived session (lazy
    import so tests that swap the DB engine pick up the current one), never
    interferes with the caller's request transaction. Mirrors the orchestrator."""
    import models
    from database import SessionLocal
    session = SessionLocal()
    try:
        session.add(models.TokenUsage(
            restaurant_id=restaurant_id,
            llm_model=resp.model,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
        ))
        session.commit()
    except Exception as exc:
        logger.warning("narrate(): failed to log token usage: %s", exc)
    finally:
        session.close()
