# Directive 108 — Product & Roadmap

**Records:** feature_request (who asked, source, link to a roadmap item), roadmap_item (target quarter as `YYYY-Qn`; `shipped_on` is set automatically), release_note.

**Agent:** signal_aggregator (deterministic). It ranks candidates by:
1. distinct requesting clients,
2. then the open deal value of those clients, per currency,
3. then the number of requests.

Deal values are read through the kernel record registry, and only if Sales is enabled; otherwise the report says "sales not enabled". Product never imports Sales (ADR 0001/0008).

**Reports:** product.signals, product.roadmap.

**Done gate:** the next restaurant-agent release is planned from OS data. Status: ⏳ open (log feature requests from tickets and deals).
