"""Money stays off storekeeper and kitchen responses.

Owner (Role.ADMIN / SUPERADMIN) and every other staff tier still receive the
full payloads. The middleware is the guarantee; routers also refuse price
fields on writes from these two tiers so a hidden number is not stored.
"""
from __future__ import annotations

import models

# Keys that carry a price, a cost, a sale, or a P&L figure. Matched by name
# at any depth of a JSON object. "total" is the order total and the PO total.
MONEY_KEYS = frozenset({
    "cost_per_unit",
    "cost_per_unit_cents",
    "cost_price",
    "total_cost",
    "value_cents",
    "price",
    "unit_price",
    "total",
    "hourly_rate",
    "revenue",
    "profit",
    "pnl",
    "amount_cents",
    "sale_price",
    "subtotal",
    "monthly_impact_cents",
    "suggested_price",
    "current_price",
    "total_cents",
    "old_price",
    "new_price",
})

HIDDEN_STAFF_ROLES = frozenset({
    models.StaffRole.STOCKKEEPER,
    models.StaffRole.KITCHEN,
})


def hides_money(user: models.User) -> bool:
    if user is None:
        return False
    if user.role in (models.Role.SUPERADMIN, models.Role.ADMIN):
        return False
    return user.staff_role in HIDDEN_STAFF_ROLES


def scrub_money(value):
    """Return a copy of JSON-like data with money keys removed at every level."""
    if isinstance(value, dict):
        return {
            key: scrub_money(item)
            for key, item in value.items()
            if key not in MONEY_KEYS
        }
    if isinstance(value, list):
        return [scrub_money(item) for item in value]
    return value


def money_keys_in(value, prefix=""):
    """Every dotted path whose final key is a money field. Used by tests."""
    found = []
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else key
            if key in MONEY_KEYS:
                found.append(path)
            found.extend(money_keys_in(item, path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(money_keys_in(item, f"{prefix}[{index}]"))
    return found
