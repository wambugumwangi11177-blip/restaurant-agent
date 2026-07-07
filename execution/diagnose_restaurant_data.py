"""
Read-only, PII-masked diagnostic (2026-07-07): figure out why the AI
dashboard shows zeros. Emails are masked (first 2 chars + domain only) and
no order contents are printed — output is aggregate counts + tenant/restaurant
mapping only. This tells us whether the logged-in account is actually
connected to the large real dataset or looking at a fresh empty restaurant.

Run: python execution/diagnose_restaurant_data.py
"""
import os
import sys

_backend = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
sys.path.insert(0, _backend)

from dotenv import load_dotenv
load_dotenv(os.path.join(_backend, ".env"))

from database import SessionLocal
import models
from sqlalchemy import func


def mask(email: str) -> str:
    if not email or "@" not in email:
        return "***"
    local, _, domain = email.partition("@")
    return f"{local[:2]}***@{domain}"


db = SessionLocal()

print("=" * 70)
print("RESTAURANTS + ORDER COUNTS (no PII)")
print("=" * 70)
rows = (
    db.query(
        models.Restaurant.id,
        models.Restaurant.tenant_id,
        func.count(models.Order.id).label("order_count"),
        func.max(models.Order.created_at).label("last_order"),
        func.min(models.Order.created_at).label("first_order"),
    )
    .outerjoin(models.Order, models.Order.restaurant_id == models.Restaurant.id)
    .group_by(models.Restaurant.id, models.Restaurant.tenant_id)
    .order_by(func.count(models.Order.id).desc())
    .all()
)
for r in rows:
    print(f"  rest_id={r.id:<4} tenant={r.tenant_id:<4} orders={r.order_count:<8} "
          f"first={str(r.first_order)[:10]} last={str(r.last_order)[:10]}")

print()
print("=" * 70)
print("USERS -> RESTAURANT THEIR TENANT OWNS (emails masked)")
print("=" * 70)
users = db.query(models.User).order_by(models.User.id).all()
for u in users:
    rests = db.query(models.Restaurant.id).filter(models.Restaurant.tenant_id == u.tenant_id).all()
    rest_ids = ", ".join(str(x.id) for x in rests) or "NONE"
    # order count for those restaurants
    oc = (
        db.query(func.count(models.Order.id))
        .join(models.Restaurant, models.Restaurant.id == models.Order.restaurant_id)
        .filter(models.Restaurant.tenant_id == u.tenant_id)
        .scalar()
    )
    print(f"  user_id={u.id:<4} {mask(u.email):<28} tenant={u.tenant_id:<4} role={u.role:<12} "
          f"rest_ids=[{rest_ids}] total_orders={oc}")

db.close()
