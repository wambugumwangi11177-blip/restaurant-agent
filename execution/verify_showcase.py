"""
Read-only, no-PII verification (2026-07-07): confirm every AI module now
returns rich insights against the live Lavy showcase data (restaurant_id=3)
after seed_showcase_restaurant.py. Aggregate numbers only.

Run: python execution/verify_showcase.py
"""
import os
import sys

_backend = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
sys.path.insert(0, _backend)
from dotenv import load_dotenv
load_dotenv(os.path.join(_backend, ".env"))

from database import SessionLocal
from ai import ops_manager, revenue_forecaster, menu_engineer, inventory_predictor, reservation_optimizer
from ai.pricing.recommendations import get_pricing_intelligence
from ai.profit.intelligence import get_profit_intelligence
from ai.labor.intelligence import get_labor_intelligence
from ai.supply_chain.intelligence import get_supply_chain_intelligence

RID = 3
db = SessionLocal()

rev = revenue_forecaster.get_revenue_forecast(db, RID)['trends']
print(f"REVENUE 30d:  KES {rev.get('total_revenue',0)/100:,.0f}   WoW {rev.get('week_over_week_growth')}%   peak={rev.get('peak_day')}")

p = get_pricing_intelligence(db, RID)['summary']
print(f"PRICING:      {p['items_analysed']} analysed, {p['total_recommendations']} recs, "
      f"{p['items_below_margin_floor']} below floor, opp KES {p['total_revenue_opportunity_cents']/100:,.0f}")

pf = get_profit_intelligence(db, RID)['summary']
print(f"PROFIT:       margin {pf.get('gross_margin_pct')}%, food cost {pf.get('food_cost_pct')}% ({pf.get('food_cost_status')}), "
      f"{pf.get('profit_leaks_found')} leaks worth KES {pf.get('total_leak_amount',0)/100:,.0f}, MoM {pf.get('revenue_mom_pct')}%")

inv = inventory_predictor.get_inventory_predictions(db, RID)['summary']
print(f"INVENTORY:    {inv.get('total_items')} items, {inv.get('critical_items')} critical, "
      f"{inv.get('low_stock_items')} low, {inv.get('high_spoilage_items')} spoilage risk")

lab = get_labor_intelligence(db, RID)['summary']
print(f"LABOR:        cost KES {lab['total_labor_cost_30d']/100:,.0f}/30d, {lab['labor_pct']}% of revenue "
      f"({lab['labor_status']}), {lab['shifts_logged']} shifts, OT KES {lab['overtime_cost_30d']/100:,.0f}")

sc = get_supply_chain_intelligence(db, RID)
scs = sc.get('summary', {})
print(f"SUPPLY CHAIN: {scs.get('total_suppliers', len(sc.get('suppliers', [])))} suppliers, "
      f"{len(sc.get('overdue_orders', []))} overdue POs, {len(sc.get('recommendations', []))} recommendations")

res = reservation_optimizer.get_reservation_insights(db, RID)
ns = res.get('no_show_analysis', {})
print(f"RESERVATIONS: no-show {ns.get('no_show_rate')}%, completion {ns.get('completion_rate')}%, "
      f"{len(res.get('recommendations', []))} recommendations")

d = ops_manager.get_operations_dashboard(db, RID)
q = d['quick_stats']
print(f"\nOPS DASHBOARD: health={d['health_score']}  today_orders={q['today_orders']}  "
      f"today_rev=KES {q['today_revenue']/100:,.0f}  30d=KES {q['total_revenue_30d']/100:,.0f}")
print(f"               risks={len(d['risks'])}  opportunities={len(d['opportunities'])}  alerts={len(d['alerts'])}")

db.close()
