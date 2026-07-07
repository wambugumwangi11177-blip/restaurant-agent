"""
Read-only validation (2026-07-07): does the analysis_anchor fix actually
produce real numbers against the 107,700-order Lavy dataset (restaurant_id=3)?
Calls the real AI functions and prints only aggregate output numbers — no PII,
no order contents. If these come back non-zero, the fix works and any zeros a
user sees are because their login account is on a DIFFERENT (empty) restaurant.

Run: python execution/verify_anchor_against_real_data.py
"""
import os
import sys

_backend = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
sys.path.insert(0, _backend)

from dotenv import load_dotenv
load_dotenv(os.path.join(_backend, ".env"))

from database import SessionLocal
from ai.analysis_clock import analysis_anchor
from ai import ops_manager, revenue_forecaster, menu_engineer
from ai.pricing.recommendations import get_pricing_intelligence

RID = 3  # Lavy — the 107,700-order restaurant

db = SessionLocal()

print(f"analysis_anchor for restaurant {RID}: {analysis_anchor(db, RID)}")
print()

rev = revenue_forecaster.get_revenue_forecast(db, RID)
t = rev.get("trends", {})
print("REVENUE FORECAST:")
print(f"  total_revenue(30d window): {t.get('total_revenue')}")
print(f"  avg_order_value: {t.get('avg_order_value')}")
print(f"  week_over_week_growth: {t.get('week_over_week_growth')}")
print()

menu = menu_engineer.get_menu_engineering(db, RID)
ms = menu.get("summary", {})
print("MENU ENGINEERING:")
print(f"  total_items: {ms.get('total_items')}  stars: {ms.get('stars')}  "
      f"dogs: {ms.get('dogs')}  avg_food_cost_pct: {ms.get('avg_food_cost_pct')}")
print()

pri = get_pricing_intelligence(db, RID)
ps = pri.get("summary", {})
print("PRICING INTELLIGENCE:")
print(f"  items_analysed: {ps.get('items_analysed')}  "
      f"total_recommendations: {ps.get('total_recommendations')}  "
      f"revenue_opportunity_cents: {ps.get('total_revenue_opportunity_cents')}")
print()

dash = ops_manager.get_operations_dashboard(db, RID)
print("OPS DASHBOARD:")
print(f"  health_score: {dash.get('health_score')}")
print(f"  quick_stats.total_revenue_30d: {dash.get('quick_stats', {}).get('total_revenue_30d')}")
print(f"  risks: {len(dash.get('risks', []))}  opportunities: {len(dash.get('opportunities', []))}")

db.close()
