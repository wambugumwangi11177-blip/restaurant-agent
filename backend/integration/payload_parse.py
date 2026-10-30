"""Parse inbound POS webhook JSON into (entity, record dicts)."""
from __future__ import annotations

from typing import Any


def records_from(payload: Any) -> tuple[str, list[dict]]:
    """
    (entity, records) from whatever shape arrived.

    Accepts an envelope with a list field, a bare list, or a single object.
    """
    if isinstance(payload, list):
        return ("unknown", [r for r in payload if isinstance(r, dict)])
    if not isinstance(payload, dict):
        return ("unknown", [])
    entity = str(payload.get("entity") or payload.get("type") or "unknown").strip() or "unknown"
    for key in ("records", "data", "items", "rows", "transactions", "sales"):
        block = payload.get(key)
        if isinstance(block, list):
            return (entity, [r for r in block if isinstance(r, dict)])
    return (entity, [payload])
