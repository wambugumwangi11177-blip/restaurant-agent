"""
backend/demo/safety.py — the demo re-seed deletes and rewrites a tenant's data, so it must never touch a real database
by accident (docs/v2/SPEC.md §0.2: "never run writes against the production DATABASE_URL").

  local   sqlite, or Postgres on localhost / 127.0.0.1 / ::1 / a unix socket      needs `--yes`
  remote  anything else (Neon, Railway, a bastion…)                               needs `--yes`, `--allow-remote`,
                                                                                  ALLOW_DESTRUCTIVE=1 and the typed
                                                                                  sentence  RESEED DEMO <host>

The target URL comes from `--database-url` or the DATABASE_URL environment variable — never from backend/.env, which in
this repository points at the live database. `describe()` prints the target with credentials stripped.
"""
from __future__ import annotations

import os
from urllib.parse import urlparse

LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", ""})


class UnsafeTarget(Exception):
    """The re-seed was refused; the message says what is missing."""


def _parts(url: str):
    parsed = urlparse(url or "")
    scheme = parsed.scheme.split("+")[0].lower()
    return scheme, (parsed.hostname or "").lower(), parsed


def classify(url: str) -> str:
    """'local' for sqlite or a Postgres on this machine, otherwise 'remote' (an empty/unparseable URL is remote: fail closed)."""
    if not url:
        return "remote"
    scheme, host, _p = _parts(url)
    if scheme == "sqlite":
        return "local"
    return "local" if host in LOCAL_HOSTS and scheme in ("postgresql", "postgres") else "remote"


def describe(url: str) -> str:
    """The URL with any credentials removed, safe to print."""
    if not url:
        return "<no database url>"
    scheme, host, parsed = _parts(url)
    if scheme == "sqlite":
        return url
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{host}{port}{parsed.path}"


def required_sentence(url: str) -> str:
    return f"RESEED DEMO {_parts(url)[1] or 'unknown-host'}"


def require_safe_target(url: str, *, yes: bool, allow_remote: bool = False, typed: str | None = None,
                        env: dict | None = None) -> str:
    """Return 'local' or 'remote' if the re-seed may proceed against `url`, else raise UnsafeTarget."""
    env = os.environ if env is None else env
    kind = classify(url)
    if not yes:
        raise UnsafeTarget("this deletes and rewrites the Demo Restaurant's data: pass --yes to confirm you mean it")
    if kind == "local":
        return kind
    missing = []
    if not allow_remote:
        missing.append("--allow-remote")
    if env.get("ALLOW_DESTRUCTIVE", "").strip() != "1":
        missing.append("ALLOW_DESTRUCTIVE=1 in the environment")
    if (typed or "").strip() != required_sentence(url):
        missing.append(f"the typed confirmation {required_sentence(url)!r}")
    if missing:
        raise UnsafeTarget(f"{describe(url)} is not a local database. Refusing without: {', '.join(missing)}")
    return kind
