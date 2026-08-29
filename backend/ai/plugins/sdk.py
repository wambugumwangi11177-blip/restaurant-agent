"""
backend/ai/plugins/sdk.py
───────────────────
Marketplace / Plugin SDK (Phase 11). Lets third parties contribute agents
(payroll, accounting, loyalty, …) that run on the platform as first-class
citizens of the Decision Intelligence stream — WITHOUT handing them the keys.

SECURITY BOUNDARY — read this before trusting a third-party plugin:
This is an in-process, COOPERATIVE capability boundary, NOT an OS-level sandbox.
A plugin handler is ordinary Python running in the host process; it could, if it
wanted, `import database` and bypass everything here. So the guardrails below are
a real, useful contract for FIRST-PARTY / REVIEWED plugins (prevent accidental
misuse, keep the interop shape honest), but they are NOT a defence against
adversarial code. Running genuinely untrusted third-party plugins safely requires
a hard isolation boundary (subprocess, container, or WASM) — that is deliberately
future work, and until it exists only vetted plugins should be registered.

Guardrails (within that cooperative model):
  • Read-only context. The handler is handed a `PluginContext` exposing only
    whitelisted read helpers — it is not passed the raw DB session, so a
    well-behaved plugin has no write surface it was GIVEN (see the caveat above
    on what it can still reach on its own).
  • Declared scopes. A manifest lists the read scopes it needs; invocation
    refuses any scope outside the platform allowlist.
  • Human-approval for mutation. A plugin that declares `mutating=True` cannot
    act directly — it can only PROPOSE `Decision`s / workflow steps, which go
    through the same owner-approval hop as the core agents.
  • Fault isolation. A plugin raising is caught and reported; it can never crash
    the host request or another plugin.

Interop surface: a plugin that `provides` "decisions" returns a list of dicts
shaped like `Decision` — they flow into the same ranking as the built-in agents.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable

from sqlalchemy.orm import Session

logger = logging.getLogger("ai.plugins")

# The only read scopes a plugin may request. A manifest asking for anything else
# is rejected at registration — the platform's data boundary, not the plugin's.
ALLOWED_SCOPES = {"orders", "menu", "inventory", "decisions", "reservations", "suppliers"}

# What a plugin may declare it provides.
ALLOWED_PROVIDES = {"decisions", "tool", "workflow_step"}


@dataclass
class PluginManifest:
    name: str
    version: str
    author: str
    description: str
    provides: list[str]                      # subset of ALLOWED_PROVIDES
    scopes: list[str] = field(default_factory=list)   # subset of ALLOWED_SCOPES
    mutating: bool = False                   # if True, may only PROPOSE (approval-gated)

    def validate(self) -> None:
        bad_scopes = set(self.scopes) - ALLOWED_SCOPES
        if bad_scopes:
            raise ValueError(f"plugin '{self.name}' requests disallowed scopes: {sorted(bad_scopes)}")
        bad_provides = set(self.provides) - ALLOWED_PROVIDES
        if bad_provides:
            raise ValueError(f"plugin '{self.name}' declares unknown capabilities: {sorted(bad_provides)}")


class PluginContext:
    """
    The surface the SDK HANDS a plugin: read-only helpers, each gated on the
    plugin's declared scopes. No write method is exposed here — so a plugin that
    sticks to this context cannot mutate data. NOTE (see module docstring): this
    is not enforced against a plugin that reaches around the context (e.g. imports
    the DB layer itself). It is a cooperative boundary for vetted plugins, not a
    sandbox against hostile code.
    """

    def __init__(self, db: Session, restaurant_id: int, scopes: set[str]):
        self._db = db
        self._restaurant_id = restaurant_id
        self._scopes = scopes

    def _require(self, scope: str) -> None:
        if scope not in self._scopes:
            raise PermissionError(f"plugin lacks '{scope}' scope")

    @property
    def restaurant_id(self) -> int:
        return self._restaurant_id

    def get_menu(self) -> list[dict]:
        self._require("menu")
        import models
        items = self._db.query(models.MenuItem).filter(
            models.MenuItem.restaurant_id == self._restaurant_id).all()
        return [{"id": i.id, "name": i.name, "price": i.price,
                 "cost_price": i.cost_price, "category": i.category} for i in items]

    def get_decisions(self) -> list[dict]:
        self._require("decisions")
        from ai.decisions import get_ranked_decisions
        return get_ranked_decisions(self._db, self._restaurant_id)["decisions"]

    def get_low_stock(self) -> list[dict]:
        self._require("inventory")
        from ai.inventory_predictor import get_inventory_predictions
        data = get_inventory_predictions(self._db, self._restaurant_id)
        return [p for p in data.get("predictions", [])
                if p.get("status") in ("critical", "low", "reorder")]


@dataclass
class Plugin:
    manifest: PluginManifest
    handler: Callable[[PluginContext, dict], object]


class PluginRegistry:
    """In-process registry. A real marketplace would load signed manifests from a
    store; the invocation guardrails are identical either way."""

    def __init__(self) -> None:
        self._plugins: dict[str, Plugin] = {}

    def register(self, manifest: PluginManifest, handler: Callable) -> None:
        manifest.validate()
        self._plugins[manifest.name] = Plugin(manifest=manifest, handler=handler)

    def unregister(self, name: str) -> None:
        self._plugins.pop(name, None)

    def clear(self) -> None:
        self._plugins.clear()

    def list(self) -> list[dict]:
        return [
            {
                "name": p.manifest.name, "version": p.manifest.version,
                "author": p.manifest.author, "description": p.manifest.description,
                "provides": p.manifest.provides, "scopes": p.manifest.scopes,
                "mutating": p.manifest.mutating,
            }
            for p in self._plugins.values()
        ]

    def get(self, name: str) -> Plugin | None:
        return self._plugins.get(name)

    def invoke(self, name: str, db: Session, restaurant_id: int,
               payload: dict | None = None, approved: bool = False) -> dict:
        plugin = self._plugins.get(name)
        if plugin is None:
            return {"available": False, "error": f"Plugin '{name}' not found."}

        # A mutating plugin may only run behind an explicit human approval; even
        # then it can only return proposals (Decisions) — it has no write surface.
        if plugin.manifest.mutating and not approved:
            return {"available": False, "requires_approval": True,
                    "error": f"Plugin '{name}' proposes changes and needs owner approval to run."}

        ctx = PluginContext(db, restaurant_id, set(plugin.manifest.scopes))
        try:
            result = plugin.handler(ctx, payload or {})
        except PermissionError as exc:
            return {"available": False, "error": f"permission denied: {exc}"}
        except Exception as exc:  # noqa: BLE001 — isolate a faulty plugin
            logger.warning("plugin '%s' raised: %s", name, exc)
            return {"available": False, "error": f"plugin error: {exc}"}

        return {"available": True, "plugin": name, "provides": plugin.manifest.provides,
                "result": result}


# Process-wide registry (mirrors how events/bus.py keeps one registry).
registry = PluginRegistry()


def _safe_int(value: object, default: int) -> int:
    """Convert *value* to int, returning *default* on any failure."""
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _safe_impact(value: object) -> int | None:
    """Return *value* as int if convertible, else None."""
    if value is None:
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def collect_plugin_decisions(db: Session, restaurant_id: int):
    """
    Invoke every registered read-only plugin that `provides` "decisions" and
    return their contributions as `Decision` objects, ready to join the built-in
    ranking. Mutating plugins are skipped here (they need approval and are invoked
    explicitly). Malformed plugin output is dropped, never trusted blindly.
    """
    from ai.decisions.model import Decision
    out: list[Decision] = []
    for p in registry._plugins.values():  # noqa: SLF001 — same-module access
        if "decisions" not in p.manifest.provides or p.manifest.mutating:
            continue
        res = registry.invoke(p.manifest.name, db, restaurant_id)
        if not res.get("available"):
            continue
        for d in res.get("result") or []:
            if not isinstance(d, dict) or "action" not in d:
                continue
            try:
                out.append(Decision(
                    agent=f"plugin:{p.manifest.name}",
                    category=d.get("category", "plugin"),
                    action=str(d["action"]),
                    rationale=str(d.get("rationale", "")),
                    confidence_pct=_safe_int(d.get("confidence_pct", 50), 50),
                    risk=_safe_int(d.get("risk", 3), 3),
                    difficulty=_safe_int(d.get("difficulty", 3), 3),
                    impact_cents_month=_safe_impact(d.get("impact_cents_month")),
                    data_sources=[f"plugin:{p.manifest.name}"],
                ))
            except Exception as exc:  # noqa: BLE001 — isolate a single bad decision dict
                logger.warning(
                    "plugin '%s' produced an invalid decision dict (skipped): %s",
                    p.manifest.name, exc,
                )
    return out