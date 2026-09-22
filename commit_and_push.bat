@echo off
cd /d "C:\Users\Administrator\restaurant-agent\restaurant-agent"
echo === Git Status ===
git status --short
echo.
echo === Adding all changes ===
git add -A
echo.
echo === Committing ===
git commit -m "fix: declare reminder_status on ReservationOut, add ECC eslint ignores, configure frontend API URL"
echo.
echo === Pushing ===
git push origin feat/pos-offline-pin-hardening
echo.
echo === Done ===
pause
