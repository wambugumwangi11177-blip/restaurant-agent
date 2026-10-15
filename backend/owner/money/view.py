"""
backend/owner/money/view.py — the P&L as the owner sees it (docs/v2/SPEC.md S3.2, §3.4 vocabulary).

`compute_pnl` (owner/money/pnl.py) speaks integer cents and system keys. This turns one result into the block Home, the
monthly report and `GET /owner/money/pnl` all share: KES at the edge, owner words, a state on the block, the lines of the
waterfall in order, and plain sentences for everything the numbers do not say by themselves ("Wages are worked out from your
shift records"). One shaper, so the three surfaces cannot disagree.
"""
from __future__ import annotations

from datetime import date, datetime

from owner.money.ledger import to_kes
from owner.states import assume, block, iso, no_data
from owner.settings import Settings

MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")


def period_label(kind: str, start: date, end: date, partial: bool) -> str:
    if kind == "day":
        return f"{start.day} {MONTHS[start.month - 1][:3]} {start.year}"
    if kind == "week":
        return f"{start.day}–{end.day} {MONTHS[end.month - 1][:3]} {end.year}" if start.month == end.month else \
            f"{start.day} {MONTHS[start.month - 1][:3]} – {end.day} {MONTHS[end.month - 1][:3]} {end.year}"
    if kind == "month":
        return f"{MONTHS[start.month - 1]} {start.year}" + (" so far" if partial else "")
    return f"{start.year}" + (" so far" if partial else "")


def _k(cents: int) -> float:
    return to_kes(cents)


def owner_pnl(p: dict, kind: str, settings: Settings, *, as_of: datetime | None = None, sales_state: str = "live") -> dict:
    """The owner-facing P&L block for one `compute_pnl` result (`kind` is day | week | month | year)."""
    period = p["period"]
    label = period_label(kind, period["start"], period["end"], period["partial"])
    sales, ingredients, gross = p["sales_cents"], p["ingredients_cents"], p["gross_profit_cents"]
    labour, other, kept = p["labour_cents"], p["other_costs_cents"], p["operating_profit_cents"]

    notes: list[str] = []
    if p["labour_basis"] == "shifts":
        notes.append("Wages are worked out from your shift records. Enter your salaries to use your real payroll.")
    elif p["labour_basis"] == "none":
        notes.append("No wages recorded for this period yet.")
    if p["ingredients_basis"] == "purchases":
        notes.append("Most dishes have no ingredient cost yet, so ingredients are what you bought in this period.")
    if p["missing_costs"]:
        names = ", ".join(m["dish"] for m in p["missing_costs"][:3])
        notes.append(f"{len(p['missing_costs'])} dish(es) you sold have no ingredient cost, so their cost counts as nothing: {names}.")
    if p["delivery_commission_basis"] == "estimated":
        notes.append("Delivery app commissions are estimated from your commission rates. Enter the real ones to replace the estimate.")
    for m in p["missing_categories"]:
        notes.append(f"No {m['name'].lower()} entered for this period — you entered it before.")
    if period["partial"]:
        notes.append(f"{label} ({period['days_elapsed']} of {period['days']} days).")

    complete = p["costs_entered"] and not p["missing_categories"] and not p["missing_costs"]
    lines = [
        {"key": "sales", "label": "Sales", "kes": _k(sales), "state": sales_state},
        {"key": "ingredients", "label": "Ingredients", "kes": -_k(ingredients), "state": "live" if p["ingredients_basis"] == "recipe" else "as_entered"},
        {"key": "left_after_ingredients", "label": "Left after ingredients", "kes": _k(gross), "subtotal": True},
        {"key": "wages", "label": "Wages", "kes": -_k(labour), "state": {"entered": "as_entered", "shifts": "live", "none": "no_data"}[p["labour_basis"]]},
        {"key": "other_costs", "label": "Other costs", "kes": -_k(other), "state": "as_entered" if p["sections"] else "no_data"},
        {"key": "kept", "label": "What you kept", "kes": _k(kept), "total": True},
    ]
    body = {
        "period": {"kind": kind, "label": label, "start": period["start"].isoformat(), "end": period["end"].isoformat(), "days": period["days"],
                   "days_elapsed": period["days_elapsed"], "partial": period["partial"]},
        "orders": p["orders"],
        "lines": lines,
        "sales_split": {"food": _k(p["food_sales_cents"]), "drinks": _k(p["drinks_sales_cents"]), "other": _k(p["other_income_cents"])},
        "sections": [{"key": s["key"], "name": s["name"], "kes": _k(s["total_cents"]),
                      "lines": [{"key": l["key"], "name": l["name"], "kes": _k(l["amount_cents"]), "entries": l["entries"], "is_fixed": l["is_fixed"],
                                 **({"basis": l["basis"]} if "basis" in l else {})} for l in s["lines"]]} for s in p["sections"]],
        "delivery_commission": {"kes": _k(p["delivery_commission_cents"]), "basis": p["delivery_commission_basis"]},
        "out_of_every_100": {"ingredients": p["food_cost_pct"], "wages": p["labour_pct"], "other_costs": p["other_costs_pct"], "kept": p["kept_pct"]},
        "ratios": {"food_cost_pct": p["food_cost_pct"], "labour_pct": p["labour_pct"], "prime_cost_pct": p["prime_cost_pct"],
                   "gross_margin_pct": p["gross_margin_pct"], "kept_pct": p["kept_pct"]},
        "basis": {"ingredients": p["ingredients_basis"], "wages": p["labour_basis"], "delivery_commission": p["delivery_commission_basis"]},
        "complete": complete,
        "missing_categories": p["missing_categories"],
        "missing_costs": [{"dish": m["dish"], "units": m["units"], "sales": _k(m["sales_cents"])} for m in p["missing_costs"]],
        "notes": notes,
        "assumptions": [assume("food_cost_target_pct", settings.food_cost_target_pct, label="Ingredient cost target"),
                        assume("prime_cost_target_pct", settings.prime_cost_target_pct, label="Ingredients + wages target"),
                        assume("labour_target_pct", settings.labour_target_pct, label="Wages target")],
    }
    if not sales and not p["costs_entered"] and not labour:
        return no_data("Nothing recorded in this period yet.", **body)
    if not p["costs_entered"]:
        return block("no_data", as_of=as_of, reason="Enter your rent, electricity and other costs to see what you kept.", **body)
    return block("as_entered", as_of=as_of, entered_up_to=iso_date(p["entered_up_to"]), **body)


def iso_date(d: date | None) -> str | None:
    return None if d is None else d.isoformat()
