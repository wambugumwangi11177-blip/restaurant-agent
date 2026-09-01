@echo off
REM Same as run_tests.bat, but pauses at the end so double-clicking this file
REM keeps the window open and the results readable.
cd /d "%~dp0backend"
python -m pytest -q
pause
