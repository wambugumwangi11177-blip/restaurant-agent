// demo-data.ts
// Hardcoded realistic demo data for Lavy restaurant.
// Used when real data is empty or below threshold.

export const demoData = {
  dashboard: {
    health_score: 84,
    health_breakdown: [
      { category: "Menu Health", score: 88 },
      { category: "Revenue Trend", score: 82 },
      { category: "Kitchen Efficiency", score: 79 },
      { category: "Inventory Status", score: 91 },
      { category: "Reservation Reliability", score: 78 },
    ],
    alerts: [
      { severity: "WARNING", message: "Chicken stock running low — reorder by 3pm", source: "inventory" },
      { severity: "INFO", message: "Friday dinner rush predicted — prep extra Goat Mandi", source: "kitchen" },
      { severity: "SUCCESS", message: "Food cost this week: 34.1% — Healthy range", source: "menu" },
    ],
    opportunities: [
      { opportunity: "Sticky Wings margin is 71% — promote more aggressively", detail: "High-margin item with growth potential" },
      { opportunity: "Wednesday lunch is 40% below Monday — consider a lunch special", detail: "Targeted promotion can boost midweek sales" },
      { opportunity: "3 customers haven't returned in 21 days — winback messages ready", detail: "Re-engage lapsed customers with personalised offers" },
    ],
    risks: [
      { risk: "Stock-out risk", severity: "high", detail: "Chicken is at 3kg — estimated 4 hours of service left" },
    ],
    quick_stats: {
      today_revenue: 5240000,   // in cents (KES 52,400)
      today_orders: 47,
      avg_order_value: 211400,  // in cents (KES 2,114)
      active_alerts: 1,
      pending_orders: 3,
      menu_items: 42,
      day_over_day_change: 12,
    },
  },

  revenue: [
    { date: "Mon", revenue: 38200, orders: 34 },
    { date: "Tue", revenue: 41500, orders: 38 },
    { date: "Wed", revenue: 44800, orders: 41 },
    { date: "Thu", revenue: 49200, orders: 45 },
    { date: "Fri", revenue: 87400, orders: 79 },
    { date: "Sat", revenue: 124600, orders: 112 },
    { date: "Sun", revenue: 98300, orders: 89 },
  ],

  topSellers: [
    { name: "Sticky Wings", orders: 156, revenue: 185640, margin: 71 },
    { name: "Goat Mandi", orders: 134, revenue: 281400, margin: 58 },
    { name: "Highwayman Burger", orders: 128, revenue: 152320, margin: 64 },
    { name: "Passion Mojito", orders: 187, revenue: 89760, margin: 73 },
    { name: "Chicken Biryani", orders: 119, revenue: 141610, margin: 62 },
  ],

  profitIntelligence: {
    summary: {
      total_profit_30d: 1847200,
      average_margin: 61.4,
      food_cost_percent: 34.1,
      food_cost_status: "HEALTHY",
      profit_leaks_found: 2,
      total_leak_amount: 38400,
    },
    stars: ["Sticky Wings", "Passion Mojito", "Goat Mandi"],
    dogs: ["Greek Salad", "Oats Porridge"],
    profit_leaks: [
      {
        title: "Fish and Chips undermargin",
        description: "Food cost at 52% — above healthy threshold",
        monthly_impact: 24800,
        action: "Increase price from KES 1,490 to KES 1,690",
      },
      {
        title: "Large Platter food cost spike",
        description: "Portion sizes inconsistent — cost varies 18%",
        monthly_impact: 13600,
        action: "Standardize portioning with kitchen guide",
      },
    ],
  },

  pricingIntelligence: {
    summary: {
      revenue_opportunity: 87400,
      surge_opportunities: 4,
      underpriced_items: 3,
    },
    recommendations: [
      {
        item: "Sticky Wings",
        current_price: 1190,
        suggested_price: 1390,
        when: "Friday & Saturday evenings",
        monthly_impact: 31200,
        type: "SURGE",
      },
      {
        item: "Goat Mandi",
        current_price: 2100,
        suggested_price: 2400,
        when: "Weekend lunch and dinner",
        monthly_impact: 28400,
        type: "SURGE",
      },
      {
        item: "Caffe Latte",
        current_price: 320,
        suggested_price: 380,
        when: "All times",
        monthly_impact: 14200,
        type: "REPRICE",
      },
    ],
  },

  whatsappBrain: {
    message:
      "🌅 Good morning James!\n\n📊 Yesterday at Lavy\nRevenue: KES 52,400\nOrders: 47 (+12% vs last Thursday)\n\n🏆 Top Sellers:\n1. Sticky Wings — 18 orders\n2. Passion Mojito — 23 orders\n3. Goat Mandi — 11 orders\n\n💰 Payments:\nM-Pesa: 61% | Cash: 24% | Card: 15%\n\n⚠️ Alerts:\n• Chicken stock low — reorder by 3pm\n\n🎯 Today's Recommendation:\nToday is Friday — your busiest day. Goat Mandi sells 3x more on Friday evenings. Ensure extra stock is prepped by 6pm.\n\nPowered by Leviii AI 🤖",
    generated_at: "Today 8:00 AM",
  },

  stockAlerts: [
    { item: "Chicken", quantity: "3kg", unit: "kg", hours_left: 4, urgency: "URGENT" },
    { item: "Passion Fruit", quantity: "2kg", unit: "kg", hours_left: 11, urgency: "WARNING" },
  ],

  winback: {
    count: 3,
    candidates: [
      { name: "Aisha Mohamed", days_since: 24, favourite: "Prawns Tagliatelle", spend: 8400 },
      { name: "Brian Mwangi", days_since: 28, favourite: "Highwayman Burger", spend: 6200 },
      { name: "Grace Wambui", days_since: 22, favourite: "Lotus Biscoff Shake", spend: 4800 },
    ],
  },
};

/**
 * Returns true only for a genuinely empty/new restaurant — no menu set up
 * and no revenue in the last 30 days. Previously checked `today_orders === 0`,
 * which meant ANY day with no live order flow (a quiet day, or — as found
 * 2026-07-07 for a real restaurant whose bulk-imported historical data
 * simply doesn't extend into "today" — every day after the dataset's last
 * date) permanently masked real health score/alerts/revenue history behind
 * the same hardcoded demo numbers. That's what "dashboard shows the same
 * data for months" was: not a caching bug, a wrong emptiness heuristic.
 */
export function isDashboardEmpty(data: any): boolean {
  if (!data) return true;
  const qs = data.quick_stats || {};
  return !qs.menu_items && !qs.total_revenue_30d;
}

/** Returns true when real orders list is empty */
export function isOrdersEmpty(orders: any[]): boolean {
  return !orders || orders.length === 0;
}
