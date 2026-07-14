"""
backend/ai/plugins/examples.py
────────────────────────────────
A reference community plugin, to document the contract and exercise the SDK. NOT
auto-registered — a deployment opts in by calling register_examples(), exactly as
it would install a real marketplace plugin. Kept read-only.
"""

from __future__ import annotations

from .sdk import PluginManifest, PluginContext, registry


HAPPY_HOUR = PluginManifest(
    name="happy_hour_suggester",
    version="1.0.0",
    author="Community",
    description="Suggests a happy-hour promo on the highest-margin drink to lift slow-hour sales.",
    provides=["decisions"],
    scopes=["menu"],
    mutating=False,
)


def _happy_hour_handler(ctx: PluginContext, _payload: dict) -> list[dict]:
    """Pick the highest-margin 'drink'/'beverage' item and propose a happy hour."""
    menu = ctx.get_menu()
    drinks = [m for m in menu
              if (m.get("category") or "").lower() in ("drink", "drinks", "beverage", "beverages")
              and m.get("price") and m.get("cost_price") is not None]
    if not drinks:
        return []
    best = max(drinks, key=lambda m: (m["price"] - (m["cost_price"] or 0)) / max(m["price"], 1))
    return [{
        "action": f"Run a happy-hour on {best['name']}",
        "rationale": "Highest-margin drink — a slow-hour discount lifts volume with room to spare.",
        "category": "marketing",
        "confidence_pct": 55,
        "risk": 2,
        "difficulty": 1,
    }]


def register_examples() -> None:
    registry.register(HAPPY_HOUR, _happy_hour_handler)
