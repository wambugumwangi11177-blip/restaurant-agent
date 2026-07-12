"""
backend/ai/graph/traverse.py
──────────────────────────────
Traversal + impact analysis over the Business Knowledge Graph (build.py).

`downstream` follows impact edges (cause → effect); `upstream` follows them in
reverse (effect → its dependencies). `impact_report` wraps a downstream sweep
into an owner-readable summary: which dishes/categories a supplier or ingredient
touches, how much 30-day revenue rides on the CRITICAL dependencies, and the
path that connects them.

Deterministic. No LLM. Magnitudes come straight from the graph node attrs, which
came straight from the tables — nothing is invented here.
"""

from __future__ import annotations

from collections import deque

from .build import Graph, node_key


def _walk(graph: Graph, start: str, edges_attr: str, forward: bool) -> tuple[set[str], list[dict]]:
    """BFS from `start` over graph.out (forward) or graph.inn (reverse). Returns
    (visited node keys excluding start, edges traversed)."""
    adjacency = graph.out if forward else graph.inn
    seen: set[str] = {start}
    order: list[str] = []
    traversed: list[dict] = []
    q = deque([start])
    while q:
        cur = q.popleft()
        for edge in adjacency.get(cur, []):
            nxt = edge["target"] if forward else edge["source"]
            traversed.append(edge)
            if nxt not in seen:
                seen.add(nxt)
                order.append(nxt)
                q.append(nxt)
    return set(order), traversed


def downstream(graph: Graph, start_key: str) -> tuple[set[str], list[dict]]:
    """Everything `start_key` affects (following impact edges forward)."""
    return _walk(graph, start_key, "out", forward=True)


def upstream(graph: Graph, start_key: str) -> tuple[set[str], list[dict]]:
    """Everything `start_key` depends on (following impact edges backward)."""
    return _walk(graph, start_key, "inn", forward=False)


def impact_report(graph: Graph, entity_type: str, ref_id) -> dict:
    """
    Owner-readable downstream impact of a supplier / ingredient / dish.

    'Revenue at risk' counts only dishes reachable through a CRITICAL ingredient
    edge — a garnish (is_critical=False) running out doesn't stop the dish, so
    counting its revenue as at-risk would overstate the blast radius.
    """
    start = node_key(entity_type, ref_id)
    if start not in graph.nodes:
        return {"available": False, "error": f"{entity_type} {ref_id} not in the knowledge graph."}

    affected_keys, edges = downstream(graph, start)

    # Which reachable dishes sit behind at least one CRITICAL edge on their path.
    critical_dishes = _dishes_via_critical_edge(graph, start)

    affected_by_type: dict[str, list[dict]] = {}
    revenue_at_risk = 0
    for key in affected_keys:
        node = graph.nodes[key]
        affected_by_type.setdefault(node["type"], []).append({
            "key": key, "label": node["label"], "attrs": node["attrs"],
        })
        if node["type"] == "menu_item" and key in critical_dishes:
            revenue_at_risk += int(node["attrs"].get("revenue_30d_cents", 0) or 0)

    return {
        "available": True,
        "root": {"key": start, "type": entity_type, "label": graph.nodes[start]["label"],
                 "attrs": graph.nodes[start]["attrs"]},
        "summary": {
            "affected_dishes": len(affected_by_type.get("menu_item", [])),
            "critical_dishes": len(critical_dishes),
            "affected_categories": len(affected_by_type.get("category", [])),
            "affected_ingredients": len(affected_by_type.get("ingredient", [])),
            "revenue_at_risk_30d_cents": revenue_at_risk,
        },
        "affected": affected_by_type,
        "edges": [
            {"source": e["source"], "relation": e["relation"], "target": e["target"], "meta": e["meta"]}
            for e in edges
        ],
    }


def _dishes_via_critical_edge(graph: Graph, start: str) -> set[str]:
    """
    Menu-item keys reachable from `start` where the ingredient→dish hop was
    CRITICAL. We BFS but only cross a `used_in` edge when is_critical is True;
    supplier→ingredient (`supplies`) and dish→category (`in_category`) edges are
    always crossable since they don't gate the dish's viability.
    """
    seen = {start}
    q = deque([start])
    critical_dishes: set[str] = set()
    while q:
        cur = q.popleft()
        for edge in graph.out.get(cur, []):
            if edge["relation"] == "used_in" and not edge["meta"].get("is_critical", False):
                continue  # non-critical ingredient: dish survives, don't flag it
            nxt = edge["target"]
            if graph.nodes[nxt]["type"] == "menu_item" and edge["relation"] == "used_in":
                critical_dishes.add(nxt)
            if nxt not in seen:
                seen.add(nxt)
                q.append(nxt)
    return critical_dishes
