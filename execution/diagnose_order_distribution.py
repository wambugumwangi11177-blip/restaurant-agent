"""
Read-only, no-PII diagnostic (2026-07-07): monthly order-count distribution
for the Lavy dataset (restaurant_id=3). Reveals where the 107,700 orders
actually are so we can anchor AI analysis to a month with real density
rather than a sparse straggler tail.

Run: python execution/diagnose_order_distribution.py
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

RID = 3
db = SessionLocal()

# Monthly counts
month = func.strftime("%Y-%m", models.Order.created_at) if db.bind.dialect.name == "sqlite" \
    else func.to_char(models.Order.created_at, "YYYY-MM")

rows = (
    db.query(month.label("m"), func.count(models.Order.id).label("c"),
             func.sum(models.Order.total).label("rev"))
    .filter(models.Order.restaurant_id == RID)
    .group_by("m")
    .order_by("m")
    .all()
)
print(f"MONTHLY ORDER DISTRIBUTION — restaurant {RID}")
print("=" * 50)
for r in rows:
    bar = "#" * min(int(r.c / 200), 60)
    print(f"  {r.m}  orders={r.c:<7} rev={r.rev or 0:<12} {bar}")

db.close()
