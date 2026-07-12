"""
backend/ai/graph/
────────────────────
Business Knowledge Graph: one connected view of suppliers → ingredients →
dishes → categories, projected from the existing tables. Deterministic and
read-only. Agents (and the CEO/Strategy agent) traverse it for cross-domain
impact instead of hand-rolling the same joins.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from .build import build_graph, Graph, node_key  # noqa: F401
from .traverse import impact_report, downstream, upstream  # noqa: F401


def get_impact(db: Session, restaurant_id: int, entity_type: str, ref_id) -> dict:
    """Build the graph and return the downstream impact of one entity."""
    graph = build_graph(db, restaurant_id)
    report = impact_report(graph, entity_type, ref_id)
    if isinstance(report, dict):
        report["graph_stats"] = graph.stats()
    return report
