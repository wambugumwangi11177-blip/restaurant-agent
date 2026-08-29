FROM python:3.12-slim

WORKDIR /app

# Install deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY . .

# Railway injects PORT at runtime as a container env var — do NOT hardcode it
# here with ENV, since that shadows Railway's actual value and causes the
# app to listen on the wrong port relative to what Railway's edge proxy
# routes to (a real 502 cause, found 2026-07-07). $PORT is read at CMD time
# from whatever the platform actually injects.
EXPOSE 8000

# This file is the SINGLE SOURCE OF TRUTH for how the backend starts.
# `Procfile` and `nixpacks.toml` were deleted 2026-07-08: railway.json pins
# "builder": "DOCKERFILE", so neither was ever read — and both disagreed with
# this file in ways that would have been silent if they ever HAD been read
# (`--workers 2`, see below, and in nixpacks.toml no migration step at all).
# Do not re-add a start command anywhere else. Change it here.
#
# railway.json uses the DOCKERFILE builder, which does NOT read Procfile's
# release phase (that's a Nixpacks/Heroku-only convention) — so migrations
# must run here, as part of container startup, or they silently never run
# on this deploy path (found 2026-07-07 — Procfile's release: line was dead
# code for this specific Railway configuration).
#
# --workers 1 (was 2, found 2026-07-07): slowapi's rate limiter uses
# in-process memory with no Redis backing it, so 2 worker processes meant 2
# independent counters — a client's requests round-robin across both,
# silently doubling every configured rate limit (login lockout protection
# was ~50% as effective as intended). Single worker makes the counter
# authoritative again; see rate_limit.py's docstring for the full tradeoff
# and the real fix (Redis-backed storage) if traffic ever needs >1 worker.
# --timeout 60: a worker whose request runs longer than this is killed and
# restarted, so a single hung upstream (LLM/Twilio/M-Pesa) can't wedge the one
# worker indefinitely. It sits above the app-level client timeouts (LLM 30s,
# Twilio 10s) so those fire first and degrade gracefully; the gunicorn timeout
# is the last-resort backstop. Tunable via GUNICORN_TIMEOUT.
CMD ["sh", "-c", "python -c 'from database import init_db; init_db()' && alembic upgrade head && gunicorn main:app --workers 1 --worker-class uvicorn.workers.UvicornWorker --timeout ${GUNICORN_TIMEOUT:-60} --bind 0.0.0.0:${PORT:-8000}"]