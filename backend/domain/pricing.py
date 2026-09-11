"""
backend/domain/pricing.py
─────────────────────────
Layer-2 deterministic pricing arithmetic, extracted from routers/orders.py
(AUD-002 in LAI-AUDIT-001): the order total was computed inline, verbatim, in
both create_order and create_public_order, with the two copies already
divergent (the public path filtered on MenuItem.is_available and defaulted
order_type to TAKEOUT instead of DINE_IN). One implementation, both callers.

Money here is integer cents end-to-end, same as every other money column in
models.py. No DB session, no HTTP, no LLM — pure arithmetic over the menu
rows the caller already fetched (the handlers batch-load them before calling,
so this adds no queries).

The public path's availability filter is intentionally NOT baked in here: it
is a *query* concern (which menu items may be sold), not an arithmetic one.
Instead this module provides the shared line-item builder with an
`require_available` flag so both callers pass through one code path and the
divergence (404 detail wording) stays explicit at the call site.
"""

from typing import Dict, Iterable

import models


def build_order_lines(
    order_items: Iterable,
    menu_items_by_id: Dict[int, models.MenuItem],
    require_available: bool = False,
) -> tuple[list, int]:
    """Build OrderItem rows and the integer-cents order total in one pass.

    Raises ValueError naming the missing/unavailable menu_item_id so each
    caller can translate it into its own HTTP error wording (the staff path
    says "not found", the public path says "not found or unavailable").
    """
    total = 0
    order_items_out = []
    for oi in order_items:
        menu_item = menu_items_by_id.get(oi.menu_item_id)
        if not menu_item:
            raise ValueError(f"menu_item_id:{oi.menu_item_id}")
        if require_available and not menu_item.is_available:
            raise ValueError(f"menu_item_id:{oi.menu_item_id}")
        line_total = menu_item.price * oi.quantity
        total += line_total
        order_items_out.append(models.OrderItem(
            menu_item_id=menu_item.id,
            quantity=oi.quantity,
            unit_price=menu_item.price,
        ))
    return order_items_out, total
