---
description: How to start the backend and frontend servers locally
---

# Start Local Dev Servers

## Known Issues
- **PowerShell execution policy** blocks `npm` / `npx` scripts directly. Always use `cmd /c` prefix.
- **Buffered terminal output** — uvicorn may not show output immediately but process is running. Use `netstat` to verify port binding.
- **Backend venv** — always use the venv Python at `backend\venv\Scripts\python.exe`.
- **api.ts fallback port** — the fallback in `frontend/src/lib/api.ts` must match the backend port (8000). If changed, restart frontend.
- **Role enum** — when creating users in scripts, always use `models.Role.ADMIN` (not string `"owner"`). Valid values: `SUPERADMIN`, `ADMIN`, `STAFF`.
- **Inline Python in PowerShell** — PowerShell mangles Python f-strings and `from` keywords. Always write a `.py` script file in `backend/.tmp/` and run it with `cmd /c ".\venv\Scripts\python.exe .tmp\script.py"`.

## Steps

// turbo-all

1. Kill any existing processes on ports 3000 and 8000 if needed:
```
netstat -ano | findstr ":3000 :8000"
```

2. Start the backend (from project root):
```
cmd /c ".\venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000"
```
Run this from `backend/` directory.

3. Start the frontend (from project root):
```
cmd /c "npx next dev --port 3000"
```
Run this from `frontend/` directory.

4. Verify both are running:
```
netstat -ano | findstr ":3000 :8000"
```
Both ports should show LISTENING.

5. Open in browser:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000

## Environment
- Frontend `.env.local`: `NEXT_PUBLIC_API_URL=http://127.0.0.1:8000`
- Backend uses SQLite at `backend/restaurant.db`
