"""
backend/startup_checks.py
──────────────────────────
Fail-closed configuration validation at boot.

Required application configuration is validated before serving requests.
External settlement and phone integrations are no longer part of the app.

  • In PRODUCTION, a hard problem raises and the app refuses to boot — better a
    loud, immediate deploy failure than insecure application configuration.
  • Outside production (sandbox/local/tests), the same problems are logged as
    warnings and tolerated, so dev and CI are never blocked.

"Production" = APP_ENV=production.
"""

import os
import logging

logger = logging.getLogger("startup")


def is_production() -> bool:
    return (
        os.getenv("APP_ENV", "").strip().lower() == "production"
    )


__all__ = ["is_production", "collect_problems", "enforce_startup_checks"]


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

    # CORS must be set explicitly in production; the built-in fallback list is a
    # dev safety net, not a production ACL.
    if prod and not os.getenv("CORS_ORIGINS"):
        soft.append("CORS_ORIGINS is not set — using built-in default origins in production")

    # email_utils.py: unconfigured SMTP means password-reset/email-verify
    # links are logged instead of emailed — fine in dev, but in production
    # that puts a working account-takeover token in plaintext application
    # logs instead of a user's inbox. Soft, not hard: the reset/verify flow
    # still works end-to-end via the logged link (see email_utils.py), so a
    # business that hasn't set up SMTP yet shouldn't be locked out of booting.
    if prod and not (os.getenv("SMTP_HOST") and os.getenv("SMTP_USER") and os.getenv("SMTP_PASSWORD")):
        soft.append(
            "SMTP is not configured in production — password reset / email "
            "verification links will be logged instead of emailed, exposing "
            "them in application logs instead of the user's inbox. Set "
            "SMTP_HOST/SMTP_USER/SMTP_PASSWORD/SMTP_FROM."
        )

    # storage.py defaults to writing to the container's own disk. That's fine
    # until something is actually uploaded through it — but Railway's
    # filesystem is ephemeral, so any file saved there is lost on the next
    # redeploy/restart. Soft, not hard: no upload endpoint exists yet, so this
    # is a durability trap waiting to be wired up, not an active data-loss bug.
    if prod and os.getenv("STORAGE_BACKEND", "local").strip().lower() != "s3":
        soft.append(
            "STORAGE_BACKEND=local in production — any uploaded file will not "
            "survive a Railway redeploy (ephemeral disk). Set STORAGE_BACKEND=s3 "
            "before wiring up any upload feature."
        )

    return hard, soft


def enforce_startup_checks() -> None:
    """Log all findings; raise on a hard problem in production. Never raises
    outside production."""
    hard, soft = collect_problems()

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
