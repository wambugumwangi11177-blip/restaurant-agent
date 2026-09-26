#!/usr/bin/env bash
# Local dev: migrate, then run API (:8000) and web shell (:3000). Ctrl-C stops both.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT/backend"
[ -d .venv ] || { python3 -m venv .venv && .venv/bin/pip install -q -r requirements-dev.txt; }
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload --port 8000 &
API=$!
trap 'kill $API 2>/dev/null' EXIT
cd "$ROOT/frontend"
[ -d node_modules ] || npm install
BACKEND_URL=http://localhost:8000 npm run dev
