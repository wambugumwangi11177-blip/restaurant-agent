"""
Verify all AI Intelligence endpoints — Enhanced deep analytics version.
"""
import requests
import json
import sys

BASE = "http://localhost:8005"

def verify():
    # Login first
    print("Logging in as admin@leviii.ai...")
    try:
        r = requests.post(f"{BASE}/auth/login", data={"username": "admin@leviii.ai", "password": "admin123"}, timeout=10)
    except requests.ConnectionError:
        print("ERROR: Cannot connect to backend. Is it running on port 8005?")
        return False
    if r.status_code != 200:
        print(f"Login failed: {r.status_code} {r.text}")
        return False
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print(f"Got token: {token[:20]}...\n")

    endpoints = [
        "/ai/dashboard",
        "/ai/menu-engineering",
        "/ai/revenue-forecast",
        "/ai/kds-intelligence",
        "/ai/inventory-predictions",
        "/ai/reservation-insights",
    ]

    results = {}
    for ep in endpoints:
        print(f"{'='*60}")
        print(f"Testing {ep}")
        print(f"{'='*60}")
        r = requests.get(f"{BASE}{ep}", headers=headers, timeout=30)
        status = r.status_code
        if status == 200:
            data = r.json()
            _print_endpoint_summary(ep, data)
            results[ep] = "PASS"
        else:
            print(f"  FAILED: {status}")
            print(f"  Response: {r.text[:500]}")
            results[ep] = f"FAIL ({status})"

    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for ep, result in results.items():
        icon = "[PASS]" if result == "PASS" else "[FAIL]"
        print(f"  {icon} {ep}")

    all_pass = all(v == "PASS" for v in results.values())
    print(f"\n{'ALL 6 ENDPOINTS VERIFIED!' if all_pass else 'SOME ENDPOINTS FAILED'}")
    return all_pass


def _print_endpoint_summary(ep, data):
    if ep == "/ai/dashboard":
        print(f"  Health Score: {data.get('health_score')}/100")
        breakdown = data.get("health_breakdown", [])
        for b in breakdown:
            print(f"    {b['category']}: {b['score']}/100 (weight: {b['weight']}%) - {b.get('detail', '')}")
        qs = data.get("quick_stats", {})
        print(f"  Today Orders: {qs.get('today_orders')}")
        print(f"  30d Revenue: {qs.get('total_revenue_30d')}")
        print(f"  Active Alerts: {qs.get('active_alerts')}")
        risks = data.get("risks", [])
        print(f"  Risks: {len(risks)}")
        for r in risks:
            print(f"    [{r['severity']}] {r['risk']}: {r['detail']}")
        opps = data.get("opportunities", [])
        print(f"  Opportunities: {len(opps)}")
        for o in opps:
            print(f"    [{o['potential']}] {o['opportunity']}")

    elif ep == "/ai/menu-engineering":
        s = data.get("summary", {})
        print(f"  Items: {s.get('total_items')} | Stars: {s.get('stars')} | Plowhorses: {s.get('plowhorses')} | Puzzles: {s.get('puzzles')} | Dogs: {s.get('dogs')}")
        print(f"  Avg Food Cost: {s.get('avg_food_cost_pct')}% | Avg Margin: {s.get('avg_margin_pct')}%")
        print(f"  Menu Optimization Score: {s.get('menu_optimization_score')}/100")
        print(f"  Rising Items: {s.get('rising_items')} | Falling: {s.get('falling_items')}")
        print(f"  Recommendations: {len(data.get('recommendations', []))}")
        pareto = data.get("pareto", {})
        print(f"  Pareto: {pareto.get('items_for_80_pct')} items drive 80% of revenue ({pareto.get('concentration_ratio')}% of menu)")
        cats = data.get("category_performance", [])
        for c in cats[:3]:
            print(f"    {c['category']}: {c['revenue_share_pct']}% revenue, {c['avg_food_cost_pct']}% food cost")
        ups = data.get("upsell_pairs", [])
        print(f"  Upsell Pairs: {len(ups)}")
        for u in ups[:3]:
            print(f"    {u['item_a']} + {u['item_b']}: lift={u['lift']} ({u['strength']})")

    elif ep == "/ai/revenue-forecast":
        t = data.get("trends", {})
        print(f"  Total Revenue (30d): {t.get('total_revenue')}")
        print(f"  Avg Daily: {t.get('avg_daily_revenue')} | Avg Order: {t.get('avg_order_value')}")
        print(f"  WoW Growth: {t.get('week_over_week_growth')}%")
        print(f"  Peak Hour: {t.get('peak_hour')} | Peak Day: {t.get('peak_day')}")
        print(f"  Best Day: {t.get('best_day', {}).get('date')} ({t.get('best_day', {}).get('revenue')})")
        print(f"  Revenue By Type:")
        for rt in data.get("revenue_by_type", []):
            print(f"    {rt['type']}: {rt['share_pct']}% ({rt['orders']} orders, avg check {rt['avg_check']})")
        print(f"  Anomalies Detected: {len(data.get('anomalies', []))}")
        for a in data.get("anomalies", [])[:2]:
            print(f"    {a['date']}: {a['type']} ({a['deviation_pct']:+.1f}%)")
        fc = data.get("forecast", [])
        print(f"  7-Day Forecast:")
        for f in fc:
            print(f"    {f['day'][:3]} {f['date']}: {f['predicted_revenue']} ({f['confidence_low']}-{f['confidence_high']}) conf={f['confidence_pct']}%")

    elif ep == "/ai/kds-intelligence":
        tp = data.get("throughput", {})
        print(f"  Orders/Day: {tp.get('orders_per_day')} | Avg Prep: {tp.get('avg_prep_minutes')} min")
        print(f"  Completion Rate: {tp.get('completion_rate')}%")
        print(f"  P95 Completion: {tp.get('p95_completion_minutes')} min")
        print(f"  Stations: {len(data.get('station_performance', []))}")
        for s in data.get("station_performance", []):
            print(f"    {s['station']}: avg={s['avg_minutes']}min p95={s['p95_minutes']}min consistency={s['consistency_score']} trend={s['trend']}")
        print(f"  Bottlenecks: {len(data.get('bottlenecks', []))}")
        for b in data.get("bottlenecks", []):
            print(f"    [{b['severity']}] {b['station']}: +{b['above_avg_by']} min above avg, impact={b['impact_score']}")
        eff = data.get("efficiency_ratings", [])
        for e in eff:
            print(f"    Station {e['station']}: {e['rating']} ({e['efficiency_pct']}%)")
        print(f"  Recommendations: {len(data.get('recommendations', []))}")

    elif ep == "/ai/inventory-predictions":
        s = data.get("summary", {})
        print(f"  Items: {s.get('total_items')} | Value: {s.get('total_inventory_value')}")
        print(f"  Monthly Spend: {s.get('total_monthly_spend')}")
        print(f"  Critical: {s.get('critical_items')} | Low: {s.get('low_stock_items')} | Reorder: {s.get('reorder_items')} | OK: {s.get('ok_items')}")
        print(f"  Fast Movers: {s.get('fast_movers')} | Slow: {s.get('slow_movers')}")
        abc = s.get("abc_breakdown", {})
        print(f"  ABC: A={abc.get('A',0)} B={abc.get('B',0)} C={abc.get('C',0)}")
        print(f"  Alerts: {s.get('alerts_count')}")
        cats = data.get("category_stats", {})
        by_vel = cats.get("by_velocity", {})
        for v, d in by_vel.items():
            print(f"    {v}: {d['count']} items ({', '.join(d.get('items', [])[:3])})")
        hm = data.get("heatmap", [])
        print(f"  Heatmap (worst 3):")
        for h in hm[:3]:
            print(f"    {h['name']}: health={h['health']} status={h['status']} abc={h['abc_class']}")

    elif ep == "/ai/reservation-insights":
        ns = data.get("no_show_analysis", {})
        print(f"  Total Reservations: {ns.get('total_reservations')}")
        print(f"  No-Show Rate: {ns.get('no_show_rate')}% | Cancel Rate: {ns.get('cancel_rate')}% | Completion: {ns.get('completion_rate')}%")
        dep = ns.get("deposit_analysis", {})
        if dep:
            wd = dep.get("with_deposit", {})
            wod = dep.get("without_deposit", {})
            print(f"  Deposit Effect: w/deposit {wd.get('no_show_rate')}% vs w/o {wod.get('no_show_rate')}% no-show")
        ri = data.get("revenue_impact", {})
        print(f"  Revenue Lost to No-Shows: {ri.get('estimated_revenue_lost')}")
        print(f"  Avg Spend/Guest: {ri.get('avg_spend_per_guest')}")
        rp = data.get("revpash", {})
        print(f"  RevPASH: {rp.get('revpash')} | Covers/Day: {rp.get('avg_covers_per_day')}")
        lt = data.get("lead_time_analysis", {})
        print(f"  Booking Lead: avg={lt.get('avg_days')} days, {lt.get('same_day_pct')}% same-day")
        ob = data.get("overbooking", {})
        print(f"  Overbooking: recommend {ob.get('recommended_rate')}% ({ob.get('risk_level')} risk)")
        print(f"  Recommendations: {len(data.get('recommendations', []))}")

    print()


if __name__ == "__main__":
    success = verify()
    sys.exit(0 if success else 1)
