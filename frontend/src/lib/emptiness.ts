// "Is there anything to show yet?" for the operational dashboard screens. An empty account gets an honest empty state,
// never another restaurant's numbers (the old hard-coded showcase was removed with the legacy demo, docs/v2 S4.6b).

/**
 * True only for a genuinely empty/new restaurant: no menu set up and no revenue in the last 30 days. It must not look at
 * `today_orders`: a quiet day, or a restaurant whose imported history stops before today, would otherwise hide its real
 * health score, alerts and revenue history behind an empty state.
 */
export function isDashboardEmpty(
  data: { quick_stats?: { menu_items?: number; total_revenue_30d?: number } } | null
): boolean {
  if (!data) return true;
  const qs = data.quick_stats || {};
  return !qs.menu_items && !qs.total_revenue_30d;
}

/** True when the orders list is empty or not loaded. */
export function isOrdersEmpty(orders: unknown[] | null | undefined): boolean {
  return !orders || orders.length === 0;
}
