@echo off
REM Boots the FastAPI backend on http://localhost:8000 (allow ~20s for startup).
REM NOTE: backend commands MUST run from the backend\ folder - its imports are
REM flat (import models, from database import ...) and only resolve from there.
cd /d "%~dp0backend"
python main.py
