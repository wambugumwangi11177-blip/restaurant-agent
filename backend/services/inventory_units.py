"""Canonical store units for deliveries and stock items."""
from __future__ import annotations

ALLOWED_UNITS = (
    "kg",
    "g",
    "L",
    "ml",
    "pcs",
    "packet",
    "tray",
    "crate",
    "bag",
)

_ALIASES = {
    "kgs": "kg",
    "kilogram": "kg",
    "kilograms": "kg",
    "gram": "g",
    "grams": "g",
    "l": "L",
    "liter": "L",
    "litre": "L",
    "liters": "L",
    "litres": "L",
    "milliliter": "ml",
    "millilitre": "ml",
    "piece": "pcs",
    "pieces": "pcs",
    "pc": "pcs",
    "bottle": "pcs",
    "bottles": "pcs",
    "packets": "packet",
    "trays": "tray",
    "crates": "crate",
    "bags": "bag",
}


def normalize_unit(raw: str | None) -> str:
    """Map legacy/free-text units to the fixed list; unknown values pass through lowercased."""
    text = (raw or "").strip()
    if not text:
        return "kg"
    key = text.lower()
    if key in _ALIASES:
        return _ALIASES[key]
    if key == "l":
        return "L"
    for allowed in ALLOWED_UNITS:
        if allowed.lower() == key:
            return allowed
    return text


def is_allowed_unit(unit: str) -> bool:
    return normalize_unit(unit) in ALLOWED_UNITS