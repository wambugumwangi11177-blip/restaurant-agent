"""
backend/owner/money/categories.py — the Kenyan restaurant P&L lines (docs/v2/SPEC.md §4 S3.1).

`pnl_line` is the section a cost is reported under; `is_fixed` says whether it belongs to the costs that do not move with
sales (rent, salaries, licences — what "costs covered" is built from, S3.3) or to the ones that do (gas, packaging, commissions).
The owner can rename, re-section or switch off any line and add their own; the standard ones are created on first use.
"""
from __future__ import annotations

import re
from typing import NamedTuple

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models

PNL_LINES = ("premises", "utilities", "staff", "fees", "operations", "marketing", "licences")
PNL_LINE_NAMES = {"premises": "Premises", "utilities": "Utilities", "staff": "Staff", "fees": "Fees and charges",
                  "operations": "Running the restaurant", "marketing": "Marketing", "licences": "Licences and permits"}


class Standard(NamedTuple):
    key: str
    name: str
    pnl_line: str
    is_fixed: bool


STANDARD: tuple[Standard, ...] = (
    Standard("premises", "Rent & premises", "premises", True),
    Standard("kplc", "Electricity (KPLC)", "utilities", True),
    Standard("water", "Water", "utilities", True),
    Standard("garbage", "Garbage collection", "utilities", True),
    Standard("gas", "Cooking gas", "utilities", False),
    Standard("charcoal", "Charcoal", "utilities", False),
    Standard("security", "Security", "operations", True),
    Standard("pos_internet", "POS & internet", "operations", True),
    Standard("repairs", "Repairs & maintenance", "operations", False),
    Standard("cleaning", "Cleaning supplies", "operations", False),
    Standard("packaging", "Packaging", "operations", False),
    Standard("delivery_commissions", "Delivery app commissions", "fees", False),
    Standard("mpesa_charges", "M-Pesa & bank charges", "fees", False),
    Standard("licences", "Licences & permits", "licences", True),
    Standard("marketing", "Marketing", "marketing", False),
    Standard("salaries", "Salaries", "staff", True),
    Standard("casuals", "Casual labour", "staff", False),
    Standard("staff_meals", "Staff meals", "staff", False),
    Standard("other", "Other costs", "operations", False),
)


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")[:40]


def ensure_categories(db: Session, restaurant_id: int) -> None:
    """Create the standard lines the restaurant does not have yet. Idempotent; safe if two requests race (the unique
    constraint decides, the loser simply finds the rows there)."""
    have = {k for (k,) in db.query(models.ExpenseCategory.key).filter(models.ExpenseCategory.restaurant_id == restaurant_id)}
    missing = [(i, s) for i, s in enumerate(STANDARD) if s.key not in have]
    if not missing:
        return
    try:
        with db.begin_nested():
            for i, s in missing:
                db.add(models.ExpenseCategory(restaurant_id=restaurant_id, key=s.key, name=s.name, pnl_line=s.pnl_line,
                                              is_fixed=s.is_fixed, is_standard=True, is_active=True, sort_order=i))
            db.flush()
    except IntegrityError:
        pass                                  # a concurrent request created them first
