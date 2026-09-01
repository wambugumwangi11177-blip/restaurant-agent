@echo off
REM Runs Alembic migrations from backend\ (alembic.ini + env.py live there).
REM NOTE: migration files in backend\alembic\versions\ can NOT be run directly
REM with python (e.g. python 001_add_agent_tables.py does nothing / fails) -
REM they only execute through the alembic CLI. `python -m alembic` is used
REM instead of the bare `alembic` command so the exact interpreter that has
REM the package installed is the one that runs it.
REM NOTE: uses the `python` on PATH = system Python 3.12, which HAS alembic.
REM (.agent-reach-venv and the uv-managed Pythons do NOT have alembic installed.)
cd /d "%~dp0backend"
python -m alembic upgrade head