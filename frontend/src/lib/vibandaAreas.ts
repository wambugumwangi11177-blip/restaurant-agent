export type VibandaArea = readonly [label: string, note: string, slug: string];

export const VIBANDA_AREA_SECTIONS: { id: string; title: string; areas: readonly VibandaArea[] }[] = [
  { id: "health", title: "Restaurant health", areas: [
    ["Revenue", "Understand recorded sales", "revenue"],
    ["Orders", "See recorded restaurant orders", "orders"],
    ["Kitchen", "Follow preparation and service", "kitchen"],
    ["Stock", "Keep an eye on ingredients and supplies", "stock"],
    ["Bookings", "See reservations and expected guests", "bookings"],
    ["Team", "View schedules and attendance", "team"],
  ] },
  { id: "money", title: "Money and control", areas: [
    ["Menu & pricing", "Menu health, prices, and margin decisions", "menu"],
    ["Finance", "Recorded money movement and reconciliation", "finance"],
    ["Expenses", "Costs, when a real expense source is connected", "expenses"],
    ["Suppliers", "Supplier reliability and purchasing risks", "suppliers"],
    ["Purchasing", "Orders, commitments, and what needs a decision", "purchasing"],
    ["Cash reconciliation", "Cash, M-Pesa, and card settlement", "cash-reconciliation"],
  ] },
  { id: "sales-risk", title: "Sales and risk", areas: [
    ["Point of sale", "Sales channels and till activity", "pos"],
    ["Marketing", "Guest growth opportunities and campaigns", "marketing"],
    ["Fraud and risk", "Unusual activity and control risks", "risk"],
    ["Notifications", "Important changes and reminders", "notifications"],
  ] },
  { id: "governance", title: "Governance and setup", areas: [
    ["Business intelligence", "Forward views, decisions, and risks", "intelligence"],
    ["Data trust", "Source freshness, completeness, and reconciliation", "data-trust"],
    ["Audit trail", "Changes, approvals, and decisions", "audit"],
    ["Restaurant settings", "Profile, connections, and owner controls", "settings"],
  ] },
];

const HOME_PILLAR_AREAS = new Set(["revenue", "orders", "kitchen", "stock", "bookings", "team"]);
export const VIBANDA_HOME_LINKS: readonly VibandaArea[] = VIBANDA_AREA_SECTIONS
  .flatMap((section) => section.areas)
  .filter(([, , slug]) => !HOME_PILLAR_AREAS.has(slug));
