"""Engineering/reliability: catch the failures the report names before customers do."""
from datetime import date, timedelta

import metrics
from .. import kernel, tools  # noqa: F401

NAME = "engineering"

# Known Anthropic retirements (report, read 2026-10-12). Update from
# platform.claude.com/docs/en/about-claude/model-deprecations monthly.
RETIRING_MODELS = {"claude-haiku-4-5": date(2026, 10, 15), "claude-sonnet-4-5": date(2026, 11, 30)}
WARN_DAYS = 60
ERROR_RATE_ALERT = 0.05
MIN_REQUESTS = 50


def configured_models() -> set[str]:
    import os
    from ai import llm_client
    ids = set(llm_client._MODEL_TIERS["anthropic"].values())
    for k in ("ANTHROPIC_MODEL", "ANTHROPIC_MODEL_LOW", "ANTHROPIC_MODEL_MEDIUM",
              "ANTHROPIC_MODEL_HIGH", "ANTHROPIC_MODEL_CREATIVE"):
        if os.getenv(k):
            ids.add(os.getenv(k))
    return ids


def error_rate() -> tuple[int, float]:
    total = errors = 0
    with metrics._lock:
        for (_m, cls), n in metrics._requests_total.items():
            total += n
            if cls == "5xx":
                errors += n
    return total, (errors / total if total else 0.0)


def run(db, today=None):
    out, today = [], today or date.today()
    for mid in sorted(configured_models()):
        for prefix, end in RETIRING_MODELS.items():
            if mid.startswith(prefix) and (end - today).days <= WARN_DAYS:
                summary = f"Model {mid} retires {end.isoformat()}"
                if not kernel.already_proposed(db, "operator_alert", summary, 7):
                    out.append(kernel.propose(
                        db, "engineering.model_watch_agent", "operator_alert",
                        {"title": summary, "severity": "high",
                         "body": f"{(end - today).days} days left. Change ANTHROPIC_MODEL* in Railway and ai/llm_client.py."},
                        summary))
    total, rate = error_rate()
    if total >= MIN_REQUESTS and rate > ERROR_RATE_ALERT:
        summary = f"5xx rate {rate:.0%} over {total} requests ({today.isoformat()})"
        if not kernel.already_proposed(db, "operator_alert", summary, 1):
            out.append(kernel.propose(
                db, "engineering.reliability_agent", "operator_alert",
                {"title": "Elevated server errors", "severity": "critical",
                 "body": f"{summary}. Check Railway logs; roll back if a deploy preceded it (DISASTER_RECOVERY.md section 6)."},
                summary))
    return out
