"""
backend/ai/graph/build.py
───────────────────────────
Business Knowledge Graph — a materialized PROJECTION over the existing tables,
not a new datastore. It connects the entities every agent already queries in
isolation (suppliers → ingredients → dishes → categories) into one graph so a
question like "if this supplier is late, what does it hit?" is a traversal, not
a hand-rolled join in each agent.

Deterministic, read-only, rebuilt on demand from the DB. Single source of truth
stays the relational tables; this is an index over them, so it can never drift
into a second, conflicting copy of the data.

Edges point in the direction impact FLOWS (upstream cause → downstream effect):

    supplier ──supplies──▶ ingredient ──used_in──▶ dish ──in_category──▶ category

so `traverse.downstream(supplier)` answers "what does this supplier affect?" and
the reverse edges answer "what does this dish depend on?".
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session

import models
from ai.pricing.analysis import fetch_item_velocities


def node_key(node_type: str, ref_id) -> str:
    return f"{node_type}:{ref_id}"


class Graph:
    """A tiny directed multigraph. Nodes keyed by "type:id"; edges carry a
    relation label and arbitrary meta (e.g. is_critical, quantity)."""

    def __init__(self) -> None:
        self.nodes: dict[str, dict] = {}
        self.out: dict[str, list[dict]] = defaultdict(list)
        self.inn: dict[str, list[dict]] = defaultdict(list)

    def add_node(self, node_type: str, ref_id, label: str, attrs: dict | None = None) -> str:
        key = node_key(node_type, ref_id)
        if key not in self.nodes:
            self.nodes[key] = {
                "key": key, "type": node_type, "ref_id": ref_id,
                "label": label, "attrs": attrs or {},
            }
        return key

    def add_edge(self, src: str, relation: str, dst: str, meta: dict | None = None) -> None:
        if src not in self.nodes or dst not in self.nodes:
            return
        edge = {"source": src, "relation": relation, "target": dst, "meta": meta or {}}
        self.out[src].append(edge)
        self.inn[dst].append(edge)

    def stats(self) -> dict:
        return {
            "nodes": len(self.nodes),
            "edges": sum(len(v) for v in self.out.values()),
            "by_type": _count_types(self.nodes.values()),
        }


def _count_types(nodes) -> dict:
    out: dict[str, int] = defaultdict(int)
    for n in nodes:
        out[n["type"]] += 1
    return dict(out)


def build_graph(db: Session, restaurant_id: int) -> Graph:
    """Materialize the knowledge graph for one restaurant from live tables."""
    g = Graph()

    # ── Menu items + categories, with 30-day revenue as a magnitude weight ────
    velocities = fetch_item_velocities(db, restaurant_id)
    items = (
        db.query(models.MenuItem)
        .filter(models.MenuItem.restaurant_id == restaurant_id)
        .all()
    )
    for it in items:
        rev = velocities[it.id].revenue_30d if it.id in velocities else 0
        mkey = g.add_node("menu_item", it.id, it.name, {
            "price": it.price,
            "cost_price": it.cost_price or 0,
            "category": it.category or "",
            "revenue_30d_cents": rev,
        })
        if it.category:
            ckey = g.add_node("category", it.category, it.category)
            g.add_edge(mkey, "in_category", ckey)

    # ── Ingredients (inventory items) ────────────────────────────────────────
    inv_items = (
        db.query(models.InventoryItem)
        .filter(models.InventoryItem.restaurant_id == restaurant_id)
        .all()
    )
    for inv in inv_items:
        g.add_node("ingredient", inv.id, inv.item_name, {
            "quantity": inv.quantity,
            "unit": inv.unit,
            "low_stock_threshold": inv.low_stock_threshold,
        })

    # ── ingredient ──used_in──▶ dish  (MenuIngredient) ───────────────────────
    links = (
        db.query(models.MenuIngredient)
        .join(models.MenuItem, models.MenuIngredient.menu_item_id == models.MenuItem.id)
        .filter(models.MenuItem.restaurant_id == restaurant_id)
        .all()
    )
    for link in links:
        src = node_key("ingredient", link.inventory_item_id)
        dst = node_key("menu_item", link.menu_item_id)
        g.add_edge(src, "used_in", dst, {
            "is_critical": bool(link.is_critical),
            "quantity_per_serving": link.quantity_per_serving,
        })

    # ── supplier ──supplies──▶ ingredient  (from purchase-order history) ──────
    suppliers = (
        db.query(models.Supplier)
        .filter(models.Supplier.restaurant_id == restaurant_id)
        .all()
    )
    for sup in suppliers:
        g.add_node("supplier", sup.id, sup.name, {
            "reliability_score": sup.reliability_score,
            "avg_lead_days": sup.avg_lead_days,
        })

    pos = (
        db.query(models.PurchaseOrder.supplier_id, models.PurchaseOrder.inventory_item_id)
        .filter(
            models.PurchaseOrder.restaurant_id == restaurant_id,
            models.PurchaseOrder.inventory_item_id.isnot(None),
        )
        .distinct()
        .all()
    )
    for supplier_id, inventory_item_id in pos:
        src = node_key("supplier", supplier_id)
        dst = node_key("ingredient", inventory_item_id)
        g.add_edge(src, "supplies", dst)

    return g
