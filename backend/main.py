import os
import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import orders, inventory, health, webhooks, auth, menu, analytics
# from routers import reservations # TODO
import auth as auth_utils # Keep original import too if used elsewhere, but maybe rename to avoid conflict
from middleware.timing import TimingMiddleware

# Init Sentry
sentry_dsn = os.getenv("SENTRY_DSN")
if sentry_dsn:
    sentry_sdk.init(
        dsn=sentry_dsn,
        traces_sample_rate=1.0,
    )

app = FastAPI()

# CORS — allow frontend to call backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://192.168.100.4:3000"],
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
# app.include_router(reservations.router)

@app.get("/")
def read_root():
    return {"Hello": "Restaurant Agent Backend"}