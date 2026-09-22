@echo off
cd /d "C:\Users\Administrator\restaurant-agent\restaurant-agent\backend"
echo === PYTEST ===
python -m pytest tests/ -x --tb=short -q 2>&1
