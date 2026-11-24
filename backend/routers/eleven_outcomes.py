"""Owner Eleven surfaces: plain outcomes from deterministic engines (no engine names)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import auth
import models
from ai.cash_reconciliation.intelligence import compute_reconciliation_report
from ai.inventory_predictor import get_inventory_predictions
from database import get_db
from routers.deps import get_or_create_restaurant
from routers.eleven_owner import _require_owner
from services.eleven_rules import run_eleven_rules

router = APIRouter(prefix="/eleven/outcomes", tags=["eleven-outcomes"])


@router.get("/handovers")
async def owner_handover_timeline(
    db: Session = Depends(get_db),
    current_user=Depends(auth.get_current_user),
):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    from routers.store_control import _handover_public

    rows = (
        db.query(models.KitchenHandover)
        .filter(models.KitchenHandover.restaurant_id == restaurant.id)
        .order_by(models.KitchenHandover.id.desc())
        .limit(60)
        .all()
    )
    return {"handovers": [_handover_public(db, row, current_user) for row in rows]}


@router.get("/stock")
async def stock_runout(
    db: Session = Depends(get_db),
    current_user=Depends(auth.get_current_user),
):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    preds = get_inventory_predictions(db, restaurant.id)
    items = preds.get("predictions") or []
    soon = [
        {
            "name": p.get("name") or p.get("item_name"),
            "unit": p.get("unit"),
            "days_left": p.get("days_until_depletion"),
            "status": p.get("status"),
        }
        for p in items
        if p.get("days_until_depletion") is not None and p["days_until_depletion"] <= 14
    ]
    soon.sort(key=lambda x: x["days_left"] or 99)
    low = [p for p in items if p.get("status") in ("low", "critical", "reorder")]
    return {
        "runout_within_two_weeks": soon[:12],
        "below_reorder": [{"name": p.get("name"), "unit": p.get("unit"), "on_hand": p.get("current_stock")} for p in low[:12]],
        "message": None if soon or low else "No low stock from recorded usage yet.",
    }


@router.get("/alerts")
async def alerts_outcomes(
    db: Session = Depends(get_db),
    current_user=Depends(auth.get_current_user),
):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    rules = run_eleven_rules(db, restaurant.id)
    custody = [r for r in rules if r.get("rule_id") == "R8"]
    return {"rules": rules, "custody_gaps": custody, "count": len([r for r in rules if r.get("status") == "needs_approval"])}


@router.get("/cash")
async def money_cash_outcome(
    db: Session = Depends(get_db),
    current_user=Depends(auth.get_current_user),
):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    report = compute_reconciliation_report(db, restaurant.id)
    flagged = [v for v in (report.drawer_variances or []) if getattr(v, "flagged", False)]
    if not report.drawer_variances:
        return {"drawer_matches": None, "message": "Waiting for a drawer count at close.", "difference_cents": None}
    if flagged:
        v0 = flagged[0]
        return {
            "drawer_matches": False,
            "message": "Cash count needs a look.",
            "difference_cents": v0.variance_cents,
        }
    return {"drawer_matches": True, "message": "Drawer matches cash sales.", "difference_cents": 0}