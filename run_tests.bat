@echo off
REM Runs the backend test suite (393 tests; roughly 1s/test on this machine).
cd /d "%~dp0backend"
python -m pytest -q
