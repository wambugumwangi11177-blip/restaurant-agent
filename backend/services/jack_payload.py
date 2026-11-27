"""Strip money fields from store payloads for stockkeepers (server-side, not CSS)."""
from __future__ import annotations

from typing import Any

import models

MONEY_KEYS = frozenset(
    {
        "kes",
        "kes_risk",
        "amount_cents",
        "estimated_total_cents",
        "cost_per_unit",
        "total_cost",
        "price",
        "unit_price",
        "unit_price_cents",
        "line_total_cents",
        "amount_kes",
        "revenue",
        "profit",
        "margin",
    }
)


def is_stockkeeper(user: models.User | None) -> bool:
    return bool(user and user.staff_role == models.StaffRole.STOCKKEEPER)


def strip_money_fields(payload: Any) -> Any:
    if isinstance(payload, dict):
        out: dict[str, Any] = {}
        for k, v in payload.items():
            if k in MONEY_KEYS:
                continue
            out[k] = strip_money_fields(v)
        return out
    if isinstance(payload, list):
        return [strip_money_fields(x) for x in payload]
    return payload