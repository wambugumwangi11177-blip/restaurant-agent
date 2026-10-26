import { fmtKes } from "@/lib/format";

export type RecordRow = Record<string, unknown>;
export type Column = {
  key: string;
  label: string;
  format?: "cents" | "money" | "percent" | "date" | "count";
};
export type ModuleConfig = {
  endpoint?: string;
  rows?: string[];
  columns: Column[];
  scope: string;
  empty: string;
};
const orders: Column[] = [
  { key: "id", label: "Order" },
  { key: "created_at", label: "Recorded", format: "date" },
  { key: "status", label: "Status" },
  { key: "order_type", label: "Channel" },
  { key: "total", label: "Total", format: "cents" },
  { key: "is_paid", label: "Paid" },
];
const cash: Column[] = [
  { key: "count_id", label: "Count" },
  { key: "expected_amount_cents", label: "Expected", format: "cents" },
  { key: "counted_amount_cents", label: "Counted", format: "cents" },
  { key: "variance_cents", label: "Difference", format: "cents" },
];

// Explicit contracts: only owner-relevant fields are displayed; never render
// arbitrary API keys, phone numbers, or raw JSON into a generic table.
export const DEMO_MODULES: Record<string, ModuleConfig> = {
  revenue: {
    endpoint: "/api/v1/overview/today?period=30d",
    rows: ["performance.revenue_trend"],
    columns: [
      { key: "date", label: "Date" },
      { key: "revenue", label: "Paid sales", format: "money" },
      { key: "orders", label: "Paid orders" },
    ],
    scope:
      "Daily sales for the last 7 calendar days · Nairobi time · paid, non-cancelled orders",
    empty: "Record a paid sale to begin tracking revenue.",
  },
  orders: {
    endpoint: "/api/v1/orders/",
    columns: orders,
    scope: "Latest 200 recorded orders · all statuses",
    empty: "No orders have been recorded.",
  },
  pos: {
    endpoint: "/api/v1/orders/",
    columns: orders,
    scope: "Latest 200 recorded orders · channel and payment status",
    empty: "No till transactions have been recorded.",
  },
  kitchen: {
    endpoint: "/api/v1/orders/active",
    columns: orders.filter((c) => c.key !== "is_paid" && c.key !== "total"),
    scope: "Current active kitchen queue · recorded orders",
    empty:
      "No active kitchen tickets were returned. Preparation timings are shown only when available.",
  },
  stock: {
    endpoint: "/api/v1/inventory/",
    columns: [
      { key: "item_name", label: "Ingredient" },
      { key: "quantity", label: "On hand" },
      { key: "unit", label: "Unit" },
      { key: "low_stock_threshold", label: "Reorder at" },
      { key: "par_level", label: "Target stock" },
    ],
    scope:
      "Current recorded inventory · quantities may require a physical count",
    empty:
      "Add inventory quantities and reorder thresholds to identify stock risks.",
  },
  bookings: {
    endpoint: "/api/v1/reservations/",
    columns: [
      { key: "reservation_date", label: "Date" },
      { key: "reservation_time", label: "Time" },
      { key: "party_size", label: "Guests" },
      { key: "status", label: "Status" },
      { key: "deposit_paid", label: "Deposit paid" },
    ],
    scope: "Latest 200 recorded reservations · all dates",
    empty: "No reservations have been recorded.",
  },
  team: {
    endpoint: "/api/v1/staff/",
    columns: [
      { key: "name", label: "Team member" },
      { key: "role_title", label: "Role" },
      { key: "is_active", label: "Active" },
      { key: "hourly_rate", label: "Hourly pay", format: "cents" },
    ],
    scope: "First 200 team members · roster, not attendance",
    empty: "Add team members and record shifts to review staffing.",
  },
  menu: {
    endpoint: "/api/v1/ai/menu-engineering?narrate=false",
    rows: ["matrix"],
    columns: [
      { key: "name", label: "Dish" },
      { key: "price", label: "Price", format: "cents" },
      { key: "qty_sold", label: "Units sold" },
      { key: "margin_pct", label: "Item margin", format: "percent" },
      { key: "classification", label: "Menu group" },
    ],
    scope:
      "Menu analysis · historical order window selected from recorded activity · item margin excludes operating expenses",
    empty: "Add your menu, item costs and sales to see menu performance.",
  },
  finance: {
    endpoint: "/api/v1/ai/profit?narrate=false",
    rows: ["channel_analysis"],
    columns: [
      { key: "channel", label: "Channel" },
      { key: "orders", label: "Orders" },
      { key: "revenue", label: "Revenue", format: "cents" },
      { key: "profit", label: "Contribution", format: "cents" },
      { key: "margin_pct", label: "Margin", format: "percent" },
    ],
    scope:
      "Historical non-cancelled orders, including unpaid orders · modeled item costs and channel commissions · excludes operating expenses",
    empty:
      "No channel contribution records are available. Record sales and verify item costs.",
  },
  suppliers: {
    endpoint: "/api/v1/suppliers/",
    columns: [
      { key: "name", label: "Supplier" },
      { key: "avg_lead_days", label: "Lead time (days)" },
      { key: "is_active", label: "Active" },
    ],
    scope: "Configured suppliers · reliability needs delivery history",
    empty:
      "Add suppliers and record deliveries to track purchasing reliability.",
  },
  purchasing: {
    endpoint: "/api/v1/purchase-orders/",
    columns: [
      { key: "supplier_name", label: "Supplier" },
      { key: "item_name", label: "Item" },
      { key: "quantity_ordered", label: "Quantity" },
      { key: "total_cost", label: "Commitment", format: "cents" },
      { key: "status", label: "Status" },
      { key: "expected_at", label: "Expected", format: "date" },
    ],
    scope:
      "Recorded purchase orders · commitments are separate from paid expenses",
    empty: "No purchase orders have been recorded.",
  },
  "cash-reconciliation": {
    endpoint: "/api/v1/cash-reconciliation/report",
    rows: ["drawer_variances"],
    columns: cash,
    scope: "Last 24 hours · recorded physical drawer counts",
    empty:
      "No drawer counts are available for comparison. Record a physical count before confirming cash reconciliation.",
  },
  marketing: {
    endpoint: "/api/v1/ai/marketing?narrate=false",
    rows: ["suggested_offers"],
    columns: [
      { key: "title", label: "Opportunity" },
      { key: "why", label: "Why it matters" },
      { key: "action", label: "Suggested action" },
    ],
    scope:
      "Recommendations from recorded guest and campaign activity · no messages are sent here",
    empty:
      "No marketing recommendations were returned. Guest and campaign history is needed.",
  },
  risk: {
    endpoint: "/api/v1/fraud/report",
    rows: ["payment_mismatches", "off_hours"],
    columns: [
      { key: "order_id", label: "Order" },
      { key: "reason", label: "Reason" },
      { key: "action", label: "Event" },
      { key: "created_at", label: "Recorded", format: "date" },
    ],
    scope: "Last 24 hours · order controls and payment exceptions",
    empty:
      "No payment mismatches or off-hours exceptions were returned. Review the other risk counts below.",
  },
  notifications: {
    endpoint: "/api/v1/notifications/",
    rows: ["items"],
    columns: [
      { key: "created_at", label: "Recorded", format: "date" },
      { key: "title", label: "Alert" },
      { key: "body", label: "Detail" },
      { key: "is_read", label: "Read" },
    ],
    scope: "Latest 50 notifications for your account",
    empty: "No notifications have been recorded for this account.",
  },
  intelligence: {
    endpoint: "/api/v1/overview/today?period=today",
    rows: ["attention"],
    columns: [
      { key: "domain", label: "Area" },
      { key: "title", label: "Finding" },
      { key: "why", label: "Why it matters" },
      { key: "what_to_do", label: "Next step" },
      { key: "impact", label: "Estimated impact" },
    ],
    scope:
      "Current open owner recommendations · estimates are not realized savings",
    empty:
      "No open recommendations were returned. Check analysis coverage on Home.",
  },
  "data-trust": {
    endpoint: "/api/v1/ai/data-quality",
    rows: ["issues"],
    columns: [
      { key: "item_name", label: "Dish" },
      { key: "issue", label: "Issue" },
      { key: "explanation", label: "Why it matters" },
      { key: "severity", label: "Severity" },
    ],
    scope: "Current menu cost checks · does not certify all restaurant records",
    empty:
      "No cost issues were returned. Check how many menu items were evaluated below.",
  },
  settings: {
    endpoint: "/api/v1/restaurants/",
    columns: [
      { key: "name", label: "Restaurant" },
      { key: "address", label: "Address" },
    ],
    scope:
      "Restaurant profiles accessible to your account · read-only overview",
    empty: "No restaurant profiles were returned.",
  },
  expenses: {
    columns: [],
    scope: "Expense source required",
    empty:
      "A recorded expense ledger is not connected. Food-cost estimates and purchase commitments are not a complete expense ledger.",
  },
  audit: {
    columns: [],
    scope: "Organization audit access required",
    empty:
      "The organization audit needs a configured organization. Owner acknowledgements on Home are recorded, but a complete business audit trail is not available in this view.",
  },
  support: {
    endpoint: "/api/v1/support/tickets",
    columns: [
      { key: "id", label: "Ticket" },
      { key: "subject", label: "Subject" },
      { key: "status", label: "Status" },
      { key: "created_at", label: "Opened", format: "date" },
    ],
    scope: "Support tickets accessible to your account",
    empty: "No support tickets have been recorded.",
  },
};

export function field(data: unknown, path: string): unknown {
  return path
    .split(".")
    .reduce<unknown>(
      (value, key) =>
        value && typeof value === "object"
          ? (value as RecordRow)[key]
          : undefined,
      data,
    );
}
export function recordRows(data: unknown, paths?: string[]): RecordRow[] {
  const values = paths
    ? paths.flatMap((path) => {
        const v = field(data, path);
        return Array.isArray(v) ? v : [];
      })
    : Array.isArray(data)
      ? data
      : [];
  return values.filter(
    (v): v is RecordRow => !!v && typeof v === "object" && !Array.isArray(v),
  );
}
export function cell(value: unknown, format?: Column["format"]): string {
  if (value == null || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (format === "date" && typeof value === "string") {
    const date = new Date(
      value.endsWith("Z") || /[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`,
    );
    return Number.isNaN(date.getTime())
      ? value
      : date.toLocaleString("en-KE", {
          timeZone: "Africa/Nairobi",
          dateStyle: "medium",
          timeStyle: "short",
        });
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return "—";
    if (format === "cents") return fmtKes(value / 100);
    if (format === "money") return fmtKes(value);
    if (format === "percent")
      return `${value.toLocaleString("en-KE", { maximumFractionDigits: 1 })}%`;
    return value.toLocaleString("en-KE", { maximumFractionDigits: 2 });
  }
  return typeof value === "string" ? value.replaceAll("_", " ") : "—";
}
