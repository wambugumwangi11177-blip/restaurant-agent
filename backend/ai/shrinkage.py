"""
backend/ai/shrinkage.py
──────────────────────────
Shrinkage detection — the gap between what the system expected on the shelf
and what a physical count actually found.

Pure reads, deterministic thresholds, no LLM — same shape as
ai/data_quality.py. Added 2026-08-06 as directive 007's "still open" item:
theoretical usage existed (stock_ledger.py deducts on every sale) but nothing
compared it against a physical count, so shrinkage — food walking out the
back, over-portioning, spillage, theft — was invisible.

Why "expected" already accounts for sales, and this module doesn't recompute
usage itself
─────────────────────────────────────────────────────────────────────────────
`InventoryItem.quantity` is a running total maintained by every write path:
`/receive` (IN), `/adjust` (manual correction), and
`stock_ledger.consume_for_order` (theoretical usage, from recipes × orders
sold, OUT). `StockCount.expected_quantity` is a snapshot of that running total
at the moment of counting, so `variance = counted - expected` already nets out
every sale-driven deduction since the previous count. This module aggregates
variances stock counts have already captured; it does not re-derive usage from
`StockMovement` rows, which would double the work and risk disagreeing with
the number the count itself reconciled against.

Why this aggregates rather than alarms on a single count
─────────────────────────────────────────────────────────────────────────────
One count can't distinguish a bad opening estimate, a miscount, or a one-off
spill from an actual, ongoing pattern of loss. A PATTERN — the same item
losing value count after count — is what's worth an owner's attention, so the
report sums variance across every count in the window rather than flagging
the first negative number it sees.
"""

from datetime import timedelta
from collections import defaultdict

from sqlalchemy.orm import Session

import models
from ai.analysis_clock import analysis_anchor

DEFAULT_WINDOW_DAYS = 90


def get_shrinkage_report(db: Session, restaurant_id: int, days: int = DEFAULT_WINDOW_DAYS) -> dict:
    """
    Shrinkage (and overage) value across every counted item in the window,
    ranked by cost impact, plus which items have never been counted at all —
    a data-quality flag in its own right, the same way ai/data_quality.py
    flags a missing cost_price: a number nobody has ever compared against
    reality can't be trusted either way.
    """
    now = analysis_anchor(db, restaurant_id)
    since = now - timedelta(days=days)

    all_items = db.query(models.InventoryItem).filter(
        models.InventoryItem.restaurant_id == restaurant_id
    ).all()
    item_map = {i.id: i for i in all_items}

    counts = (
        db.query(models.StockCount)
        .filter(
            models.StockCount.restaurant_id == restaurant_id,
            models.StockCount.created_at >= since,
        )
        .order_by(models.StockCount.created_at.asc())
        .all()
    )

    if not counts:
        return _empty_response(item_map, days)

    per_item: dict[int, dict] = defaultdict(lambda: {
        "variance_qty": 0.0, "loss_qty": 0.0, "gain_qty": 0.0,
        "count_events": 0, "last_counted_at": None,
    })
    for c in counts:
        bucket = per_item[c.inventory_item_id]
        bucket["variance_qty"] += c.variance
        if c.variance < 0:
            bucket["loss_qty"] += -c.variance
        elif c.variance > 0:
            bucket["gain_qty"] += c.variance
        bucket["count_events"] += 1
        bucket["last_counted_at"] = c.created_at   # counts are ascending, so this ends up latest

    items_report = []
    total_loss_cents = 0
    total_gain_cents = 0
    for item_id, bucket in per_item.items():
        item = item_map.get(item_id)
        if not item:
            continue   # item deleted since it was counted
        # cost_per_unit is whole KES (see stock_ledger.py's unit-boundary note) —
        # ×100 to reach the cents every other money figure in this app uses.
        cost = item.cost_per_unit or 0.0
        loss_cents = int(round(bucket["loss_qty"] * cost * 100))
        gain_cents = int(round(bucket["gain_qty"] * cost * 100))
        total_loss_cents += loss_cents
        total_gain_cents += gain_cents
        items_report.append({
            "inventory_item_id": item_id,
            "item_name": item.item_name,
            "unit": item.unit,
            "count_events": bucket["count_events"],
            "net_variance_qty": round(bucket["variance_qty"], 2),
            "shrinkage_qty": round(bucket["loss_qty"], 2),
            "shrinkage_value_cents": loss_cents,
            "overage_qty": round(bucket["gain_qty"], 2),
            "overage_value_cents": gain_cents,
            "last_counted_at": bucket["last_counted_at"].isoformat() if bucket["last_counted_at"] else None,
        })

    items_report.sort(key=lambda r: r["shrinkage_value_cents"], reverse=True)

    counted_ids = set(per_item.keys())
    never_counted = [
        {"inventory_item_id": i.id, "item_name": i.item_name, "unit": i.unit}
        for i in all_items if i.id not in counted_ids
    ]

    return {
        "available": True,
        "window_days": days,
        "summary": {
            "total_shrinkage_value_cents": total_loss_cents,
            "total_overage_value_cents": total_gain_cents,
            "items_counted": len(per_item),
            "items_never_counted": len(never_counted),
            "total_items": len(all_items),
        },
        "items": items_report,
        "never_counted": never_counted,
    }


def _empty_response(item_map: dict, days: int) -> dict:
    return {
        "available": True,
        "window_days": days,
        "summary": {
            "total_shrinkage_value_cents": 0,
            "total_overage_value_cents": 0,
            "items_counted": 0,
            "items_never_counted": len(item_map),
            "total_items": len(item_map),
        },
        "items": [],
        "never_counted": [
            {"inventory_item_id": i.id, "item_name": i.item_name, "unit": i.unit}
            for i in item_map.values()
        ],
    }
