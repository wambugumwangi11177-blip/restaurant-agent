"""
backend/feature_flags.py
─────────────────────────
Minimal, env-driven feature flags for safe, reversible rollout of behaviour —
the mechanism the production checklist calls for, kept deliberately simple
(no DB, no external service) to match this codebase's reliability ethos.

Each flag is declared in _FLAGS with a default and a one-line description, and
overridden at runtime by an env var `FEATURE_<NAME>` (case-insensitive truthy:
1/true/yes/on). A flag that isn't declared here is unknown and always returns
its caller-supplied default — declaring it here is what documents it and gives
it a default + a slot in the /flags API.

Design choices:
  • Global (not per-tenant): per-tenant flags would need a table + migration;
    these are process-level rollout/kill switches, read at call time from the
    environment so they can be flipped by a redeploy-free env change.
  • Fail-safe defaults: every flag's default is the SAFE state, so a missing or
    malformed env var never enables risky new behaviour.
"""

import os

# name -> (default, description)
_FLAGS: dict[str, tuple[bool, str]] = {
    # Master kill-switch for all LLM narration. Default ON. Set
    # FEATURE_AI_NARRATION=false to instantly stop every LLM call (dashboard
    # narratives, /ai/explain, the WhatsApp orchestrator fallback) and serve
    # deterministic data only — an operational cost/incident valve that needs no
    # redeploy. Safe because narration is already strictly additive.
    "ai_narration": (True, "Master switch for LLM narration; off = deterministic data only, zero LLM spend."),
    # Reserved for Phase 6 — persist WhatsApp turn history for cross-message LLM
    # context. Default OFF until the feature lands.
    "conversation_memory": (False, "Persist WhatsApp conversation history for cross-message LLM context."),
}

_TRUTHY = {"1", "true", "yes", "on"}


def is_enabled(flag: str, default: bool | None = None) -> bool:
    """True if `flag` is on. Env var FEATURE_<FLAG> overrides the registered
    default; an unregistered flag falls back to `default` (or False)."""
    registered_default = _FLAGS.get(flag, (False, ""))[0]
    fallback = registered_default if default is None else default
    raw = os.getenv(f"FEATURE_{flag.upper()}")
    if raw is None:
        return fallback
    return raw.strip().lower() in _TRUTHY


def all_flags() -> dict[str, bool]:
    """Current on/off state of every registered flag (for UI gating)."""
    return {name: is_enabled(name) for name in _FLAGS}


def flag_details() -> list[dict]:
    """Registered flags with their state + description (for an admin view)."""
    return [
        {"name": name, "enabled": is_enabled(name), "description": desc}
        for name, (_default, desc) in _FLAGS.items()
    ]
