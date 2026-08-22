#!/usr/bin/env bash
# dev.sh — start the whole stack locally with one command.
#   ./dev.sh          → backend (port 8000) + frontend (port 3000)
#   Ctrl+C            → stops both
# Backend takes ~20-40s to become ready (it syncs the schema to the remote
# Neon Postgres on boot — see RUNBOOK.md). Frontend is ready in a few seconds.
set -euo pipefail
cd "$(dirname "$0")"

# ── Pre-flight: tell you the exact fix instead of failing mysteriously ──────
if [ ! -x backend/venv/bin/python ]; then
    echo "backend/venv is missing or broken. Rebuild it:"
    echo "  cd backend && python3 -m venv venv && venv/bin/pip install -r requirements.txt"
    exit 1
fi
if ! backend/venv/bin/python -c "import fastapi" 2>/dev/null; then
    echo "backend/venv exists but its packages are missing (often a Python upgrade"
    echo "broke it). Rebuild it:"
    echo "  cd backend && rm -rf venv && python3 -m venv venv && venv/bin/pip install -r requirements.txt"
    exit 1
fi
if [ ! -d frontend/node_modules ]; then
    echo "frontend/node_modules is missing. Install it:"
    echo "  cd frontend && npm install"
    exit 1
fi

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
    echo ""
    echo "Stopping..."
    [ -n "$FRONTEND_PID" ] && kill "$FRONTEND_PID" 2>/dev/null
    [ -n "$BACKEND_PID" ] && kill "$BACKEND_PID" 2>/dev/null
    # Dev servers spawn children (next-server, uvicorn workers).
    pkill -P "$FRONTEND_PID" 2>/dev/null || true
    pkill -P "$BACKEND_PID" 2>/dev/null || true
    wait 2>/dev/null
    echo "Stopped."
}
trap cleanup EXIT INT TERM

echo "▶ Backend  → http://localhost:8000  (ready in ~20-40s; check backend.log)"
( cd backend && exec venv/bin/python -m uvicorn main:app --port 8000 > ../backend.log 2>&1 ) &
BACKEND_PID=$!

echo "▶ Frontend → http://localhost:3000  (ready in a few seconds; check frontend.log)"
( cd frontend && exec npm run dev > ../frontend.log 2>&1 ) &
FRONTEND_PID=$!

echo ""
echo "Stack starting. Ctrl+C stops both. Logs: ./backend.log ./frontend.log"
wait
