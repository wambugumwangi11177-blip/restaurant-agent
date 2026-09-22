@echo off
cd /d "C:\Users\Administrator\restaurant-agent\restaurant-agent\frontend"
echo === LINT ===
npx eslint src 2>&1
echo === TSC ===
npx tsc --noEmit 2>&1
