"""Prep v1: weekday averages from handovers, scaled by recipe lines per dish."""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from sqlalchemy.orm import Session

import models
from time_utils import utcnow


def prep_for_today(db: Session, restaurant_id: int) -> list[dict]:
    today = utcnow().date()
    weekday = today.weekday()
    since = utcnow() - timedelta(days=28)
    handovers = (
        db.query(models.KitchenHandover)
        .filter(
            models.KitchenHandover.restaurant_id == restaurant_id,
            models.KitchenHandover.created_at >= since,
        )
        .all()
    )
    by_item: dict[int, list[float]] = defaultdict(list)
    for h in handovers:
        if h.created_at and h.created_at.weekday() == weekday:
            for line in h.lines:
                by_item[line.inventory_item_id].append(float(line.quantity))
    dishes = (
        db.query(models.MenuItem)
        .filter(models.MenuItem.restaurant_id == restaurant_id)
        .limit(20)
        .all()
    )
    out: list[dict] = []
    for dish in dishes:
        lines = db.query(models.MenuIngredient).filter(models.MenuIngredient.menu_item_id == dish.id).all()
        if not lines:
            continue
        needs = []
        for ing in lines:
            item = db.query(models.InventoryItem).filter(models.InventoryItem.id == ing.inventory_item_id).first()
            if not item:
                continue
            samples = by_item.get(item.id, [])
            avg = sum(samples) / len(samples) if samples else float(item.low_stock_threshold or 1)
            yf = float(ing.yield_fraction or 1.0) or 1.0
            qty = avg * float(ing.quantity_per_serving or 1) / yf
            needs.append(
                {
                    "ingredient": item.item_name,
                    "quantity": round(qty, 2),
                    "unit": ing.recipe_unit or item.unit,
                }
            )
        if needs:
            out.append({"dish": dish.name, "ingredients": needs})
    return out


def prep_list_dated(db: Session, restaurant_id: int) -> dict:
    """Plates × recipe/yield minus recent kitchen handover qty."""
    day = utcnow().date().isoformat()
    dishes = prep_for_today(db, restaurant_id)
    kitchen_on_hand: dict[int, float] = defaultdict(float)
    last_h = (
        db.query(models.KitchenHandover)
        .filter(models.KitchenHandover.restaurant_id == restaurant_id)
        .order_by(models.KitchenHandover.id.desc())
        .first()
    )
    if last_h:
        for line in last_h.lines:
            kitchen_on_hand[line.inventory_item_id] += float(line.quantity)
    rows = []
    for dish in dishes:
        issue = []
        for need in dish.get("ingredients") or []:
            item = (
                db.query(models.InventoryItem)
                .filter(
                    models.InventoryItem.restaurant_id == restaurant_id,
                    models.InventoryItem.item_name == need["ingredient"],
                )
                .first()
            )
            if not item:
                qty = float(need["quantity"])
                if qty > 0.01:
                    issue.append({**need, "issue_qty": round(qty, 2)})
                continue
            held = kitchen_on_hand.get(item.id, 0.0)
            issue_qty = max(0.0, float(need["quantity"]) - held)
            if issue_qty > 0.01:
                issue.append(
                    {**need, "issue_qty": round(issue_qty, 2), "kitchen_has": round(held, 2)}
                )
        if issue:
            rows.append({"dish": dish["dish"], "date": day, "ingredients": issue})
    if not rows and dishes:
        return {
            "date": day,
            "rows": [],
            "message": "Nothing to issue, the kitchen has enough.",
        }
    return {"date": day, "rows": rows}