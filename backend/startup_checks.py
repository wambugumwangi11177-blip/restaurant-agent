"""
backend/startup_checks.py
──────────────────────────
Fail-closed configuration validation at boot.

Several security properties in this app depend on an env var being SET, not on
code — most importantly MPESA_CALLBACK_TOKEN: without it the M-Pesa settlement
callback is unauthenticated and forgeable (see routers/webhooks.py). Today that
gap only surfaces as a log warning when a callback happens to arrive — far too
late. This module turns those into a startup gate:

  • In PRODUCTION, a hard problem raises and the app refuses to boot — better a
    loud, immediate deploy failure than a silently forgeable payment endpoint.
  • Outside production (sandbox/local/tests), the same problems are logged as
    warnings and tolerated, so dev and CI are never blocked.

Which environment we are in is decided by environment.py — see that module for
why this was moved out of here (short version: the gate below was keying off an
APP_ENV that nothing in the repo ever set, so production never looked like
production and every hard check silently degraded to a warning).

The checks below cover the three ways this app has been observed to boot into a
state that *looks* healthy and is not:

  1. No MPESA_CALLBACK_TOKEN → the payment callback is forgeable.
  2. No DATABASE_URL → database.py falls back to a local SQLite file, so the app
     boots green against an empty throwaway database and every health check
     passes while serving no real data.
  3. No CORS_ORIGINS → main.py falls back to a built-in origin list. That list is
     a dev convenience, not a production access-control decision.
"""

import logging
import os

from environment import current_env, env_declared, is_production  # noqa: F401  (re-exported)

logger = logging.getLogger("startup")


def _mpesa_configured() -> bool:
    return all(os.getenv(k) for k in (
        "MPESA_CONSUMER_KEY", "MPESA_CONSUMER_SECRET", "MPESA_SHORTCODE", "MPESA_PASSKEY",
    ))


def collect_problems() -> tuple[list[str], list[str]]:
    """
    Return (hard_problems, soft_warnings).

    hard_problems  — block a production boot (security-critical).
    soft_warnings  — logged everywhere, never block (operational hygiene).
    """
    hard: list[str] = []
    soft: list[str] = []

    # SECRET_KEY is already enforced at import in auth.py, but check defensively
    # so this function is a complete picture of required config.
    if not os.getenv("SECRET_KEY"):
        hard.append("SECRET_KEY is not set")

    prod = is_production()

    # An environment that is only inferred is one nobody declared. Warn everywhere
    # — in production this is the difference between the checks below running and
    # being skipped, so it is worth a line in every boot log.
    if not env_declared():
        soft.append(
            f"APP_ENV is not set — environment inferred as {current_env()!r}. "
            "Set APP_ENV explicitly (local|ci|staging|production)"
        )

    # The forgeable-payment gap: if M-Pesa credentials are present, the callback
    # MUST be tokenized, or anyone with a CheckoutRequestID can forge a settlement.
    if _mpesa_configured() and not os.getenv("MPESA_CALLBACK_TOKEN"):
        msg = ("MPESA_CALLBACK_TOKEN is not set while M-Pesa is configured — the "
               "payment callback would be UNAUTHENTICATED and forgeable")
        (hard if prod else soft).append(msg)

    # Database: an unset DATABASE_URL is not a missing feature, it is a silent
    # redirect. database.py falls back to sqlite:///./restaurant.db, so a
    # production deploy with a typo'd or absent DATABASE_URL boots successfully
    # against an empty ephemeral file — health checks pass, data is gone.
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        msg = ("DATABASE_URL is not set — the app would fall back to a local "
               "SQLite file instead of the real database")
        (hard if prod else soft).append(msg)
    elif database_url.startswith("sqlite"):
        msg = f"DATABASE_URL points at SQLite ({database_url.split(':')[0]}) — not a production database"
        (hard if prod else soft).append(msg)

    # CORS must be set explicitly in production; the built-in fallback list is a
    # dev safety net (localhost origins), not a production ACL. Promoted from a
    # warning to a hard problem: leaving it soft meant production silently ran on
    # the dev origin list, which is exactly the environment bleed this gate is for.
    if not os.getenv("CORS_ORIGINS"):
        msg = "CORS_ORIGINS is not set — the built-in localhost dev origins would be used"
        (hard if prod else soft).append(msg)

    return hard, soft


def enforce_startup_checks() -> None:
    """Log all findings; raise on a hard problem in production. Never raises
    outside production."""
    hard, soft = collect_problems()

    logger.info("[startup] environment=%s (declared=%s)", current_env(), env_declared())

    for w in soft:
        logger.warning("[startup] config warning: %s", w)
    for h in hard:
        logger.error("[startup] CONFIG PROBLEM: %s", h)

    if not hard and not soft:
        logger.info("[startup] config checks passed")
        return

    if hard and is_production():
        raise RuntimeError(
            "Refusing to start in production with critical config problems: "
            + "; ".join(hard)
        )
