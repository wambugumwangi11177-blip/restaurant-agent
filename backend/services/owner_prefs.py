"""Owner app preferences stored on the restaurant row (JSON, no extra table)."""
from __future__ import annotations

import json

import models

_KEY = "__owner_v11__"
_DEFAULTS = {
    "food_cost_target_pct": 32.0,
    "monthly_sales_target_kes": 1_200_000,
    "default_par_days": 7,
    "locale": "en",
}


def read_prefs(restaurant: models.Restaurant) -> dict:
    raw = {}
    try:
        raw = json.loads(restaurant.staple_caps_json or "{}")
    except json.JSONDecodeError:
        raw = {}
    block = raw.get(_KEY) if isinstance(raw.get(_KEY), dict) else {}
    out = {**_DEFAULTS, **block}
    return out


def write_prefs(db, restaurant: models.Restaurant, patch: dict) -> dict:
    raw = {}
    try:
        raw = json.loads(restaurant.staple_caps_json or "{}")
    except json.JSONDecodeError:
        raw = {}
    block = raw.get(_KEY) if isinstance(raw.get(_KEY), dict) else {}
    block = {**block, **{k: v for k, v in patch.items() if v is not None}}
    raw[_KEY] = block
    restaurant.staple_caps_json = json.dumps(raw)
    db.add(restaurant)
    return {**_DEFAULTS, **block}


def month_ledger_key(period: str) -> str:
    return f"month_ledger_{period}"


def read_month_ledger(restaurant: models.Restaurant, period: str) -> dict | None:
    raw = {}
    try:
        raw = json.loads(restaurant.staple_caps_json or "{}")
    except json.JSONDecodeError:
        return None
    block = raw.get(_KEY) or {}
    led = block.get(month_ledger_key(period))
    return led if isinstance(led, dict) else None


def write_month_ledger(db, restaurant: models.Restaurant, period: str, payload: dict) -> dict:
    raw = {}
    try:
        raw = json.loads(restaurant.staple_caps_json or "{}")
    except json.JSONDecodeError:
        raw = {}
    block = raw.get(_KEY) if isinstance(raw.get(_KEY), dict) else {}
    block[month_ledger_key(period)] = payload
    raw[_KEY] = block
    restaurant.staple_caps_json = json.dumps(raw)
    db.add(restaurant)
    return payload