"""
backend/environment.py
───────────────────────
The single authoritative answer to "which environment is this process running in".

Why this exists: `startup_checks.is_production()` already encoded the notion of a
production environment, but it was derived from env vars that are set NOWHERE in
this repo's deploy config — `APP_ENV` appears in no Dockerfile, no railway.json,
no render.yaml, no CI workflow, and was not even documented in `.env.example`.
The practical effect was that `is_production()` returned False *in production*,
which silently downgraded the MPESA_CALLBACK_TOKEN boot gate from a hard failure
to a log warning — i.e. the one security property that gate exists to protect was
disarmed by an undeclared variable. See startup_checks.py.

The fix is not another env var read scattered through the codebase; it is one
module that every other consumer derives from, so "am I production?" has exactly
one implementation and one place to audit.

Resolution order (evaluated on every call — never cached, because tests
monkeypatch these and a cached answer would leak across tests):

  1. APP_ENV, if set — the explicit declaration, and the only one that should be
     relied on in a real deployment.
  2. MPESA_ENV=production — preserves the pre-existing inference. Real money is
     moving, so treat it as production even if nobody declared APP_ENV.
  3. CI — GitHub Actions and most runners set this.
  4. Otherwise "local".

Unrecognised APP_ENV values resolve to PRODUCTION, not LOCAL. A typo like
APP_ENV=prod must not silently unlock the permissive local-dev behaviour; the
safe failure direction for an ambiguous environment is the strict one.
"""

import logging
import os

logger = logging.getLogger(__name__)

LOCAL = "local"
CI = "ci"
STAGING = "staging"
PRODUCTION = "production"

VALID_ENVS = (LOCAL, CI, STAGING, PRODUCTION)

_TRUTHY = {"1", "true", "yes", "on"}


def env_declared() -> bool:
    """True if APP_ENV was explicitly set. Callers use this to warn about an
    environment that is only being *inferred* — see startup_checks."""
    return bool(os.getenv("APP_ENV", "").strip())


def current_env() -> str:
    """Resolve the current environment name. Always one of VALID_ENVS."""
    raw = os.getenv("APP_ENV", "").strip().lower()
    if raw:
        if raw in VALID_ENVS:
            return raw
        # Fail safe, not open: an unrecognised value is a misconfiguration, and
        # the strict environment is the safe guess.
        logger.error(
            "[env] APP_ENV=%r is not one of %s — treating this process as "
            "PRODUCTION so no safety check is skipped by a typo.",
            raw, ", ".join(VALID_ENVS),
        )
        return PRODUCTION

    # APP_ENV undeclared — infer conservatively.
    if os.getenv("MPESA_ENV", "").strip().lower() == PRODUCTION:
        return PRODUCTION
    if os.getenv("CI", "").strip().lower() in _TRUTHY:
        return CI
    return LOCAL


def is_production() -> bool:
    return current_env() == PRODUCTION


def is_staging() -> bool:
    return current_env() == STAGING


def is_local() -> bool:
    return current_env() == LOCAL


def is_ci() -> bool:
    return current_env() == CI
