/** The owner's name for every block of every area (docs/v2/SPEC.md §3.4): the keys are the API's, the words are the owner's. */
import type { AreaKey } from "./types";

export const AREA_TITLES: Record<AreaKey, string> = {
  money: "My Money", sales_dishes: "Sales & Dishes", store: "Store & Suppliers", cash: "Cash Check", staff: "Staff", permits: "Permits & Settings",
};

export const BLOCK_TITLES: Record<AreaKey, Record<string, string>> = {
  money: { food_cost: "Food cost", wages: "Wages", prime_cost: "Prime cost", pnl: "Profit & Loss", cost_dials: "Ingredients and wages", breakeven: "Costs covered", bills: "Bills coming up", spikes: "Costs going up", savings: "What LEVIII saved you" },
  sales_dishes: {
    seven_day: "Sales, last 7 days", forecast: "Next 7 days", matrix: "Best and weakest dishes", dishes_by_kes: "What each dish earns", price_ideas: "Price ideas",
    delivery: "What delivery really pays", outlook: "Next 30 days", win_back: "Winning guests back", simulator: "What if I change a price",
  },
  store: { missing: "Missing stock", handover: "Store-to-kitchen handovers", reorder: "Time to reorder", suppliers: "Suppliers" },
  cash: { shifts: "Cash count check", cancelled_sales: "Cancelled sales", below_menu_price: "Sold below menu price", mpesa: "M-Pesa check", patterns: "Recurring patterns" },
  staff: { wages: "Wages", on_shift: "On shift", kitchen: "Kitchen speed" },
  permits: { licences: "Licences", settings: "Your targets", till_connection: "Till connection", data_trust: "How complete your costs are" },
};

/** Old /vibanda/<slug> and /demo/<slug> pages → the Home panel that now holds what they showed. */
export const LEGACY_AREA: Record<string, AreaKey> = {
  revenue: "sales_dishes", orders: "sales_dishes", pos: "sales_dishes", menu: "sales_dishes", marketing: "sales_dishes", intelligence: "sales_dishes", forecast: "sales_dishes",
  stock: "store", suppliers: "store", purchasing: "store", inventory: "store",
  finance: "money", expenses: "money", costs: "money",
  "cash-reconciliation": "cash", cash: "cash", risk: "cash", fraud: "cash",
  team: "staff", staff: "staff", kitchen: "staff", bookings: "staff",
  "data-trust": "permits", audit: "permits", settings: "permits", notifications: "permits",
};
