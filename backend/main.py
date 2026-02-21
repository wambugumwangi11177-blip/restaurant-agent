import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import orders, inventory, health, webhooks, auth, menu, analytics, reservations
import auth as auth_utils
from middleware.timing import TimingMiddleware

# Init Sentry (optional — won't crash if sentry-sdk is missing or DSN is unset)
try:
    import sentry_sdk
    sentry_dsn = os.getenv("SENTRY_DSN")
    if sentry_dsn:
        sentry_sdk.init(dsn=sentry_dsn, traces_sample_rate=1.0)
except Exception:
    pass

app = FastAPI()

# Create database tables after app starts (not at import time)
@app.on_event("startup")
def on_startup():
    from database import init_db
    try:
        init_db()
        print("[OK] Database tables initialized")
    except Exception as e:
        # Log but don't crash — the port must open for Render health checks
        print(f"[WARN] DB init deferred: {e}")

# CORS — allow frontend to call backend
# Configure via CORS_ORIGINS env var (comma-separated) or use defaults
default_origins = "http://localhost:3000,http://127.0.0.1:3000,http://192.168.100.4:3000"
cors_origins = os.getenv("CORS_ORIGINS", default_origins).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in cors_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(TimingMiddleware)

app.include_router(auth.router)
app.include_router(menu.router)
app.include_router(orders.router)
app.include_router(inventory.router)
app.include_router(health.router)
app.include_router(webhooks.router)
app.include_router(analytics.router)
app.include_router(reservations.router)

@app.get("/")
def read_root():
    return {"Hello": "Restaurant Agent Backend"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)