/**
 * The blocks of the six areas as the screens read them (backend/owner/areas.py). A block with no data is only
 * `{ state, as_of, reason }`; every field below is present when its state says there is something to show.
 */
import type { Assumption, Block } from "./types";

type Money = number;                       // KES at the edge, to the cent

// ── My Money ─────────────────────────────────────────────────────────────────
export type PnlLine = { key: "sales" | "ingredients" | "left_after_ingredients" | "wages" | "other_costs" | "kept"; label: string; kes: Money; state?: string; subtotal?: boolean; total?: boolean };
export type PnlSection = { key: string; name: string; kes: Money; lines: { key: string; name: string; kes: Money; entries: number; is_fixed: boolean; basis?: string }[] };
export type PnlBlock = Block & {
  period: { kind: string; label: string; start: string; end: string; days: number; days_elapsed: number; partial: boolean };
  lines: PnlLine[];
  sections: PnlSection[];
  out_of_every_100: { ingredients: number | null; wages: number | null; other_costs: number | null; kept: number | null };
  notes: string[];
  complete: boolean;
  missing_categories: { key: string; name: string; why: string }[];
  missing_costs: { dish: string; units: number; sales: Money }[];
  delivery_commission: { kes: Money; basis: "entered" | "estimated" | "none" };
};
export type CostDialsBlock = Block & { food_cost_pct: number; food_cost_target_pct: number; food_cost_word: string; wages_pct: number; wages_target_pct: number; wages_word: string };
export type BreakEvenBlock = Block & {
  break_even_kes: Money; sales_today_kes: Money; to_go_kes: Money; covered: boolean; crossed_at: string | null; fixed_per_day_kes: Money; food_cost_pct: number; note: string;
  built_from: { label: string; period: string; days: number; fixed_costs_kes: Money; wages_kes: Money; lines: { name: string; kes: Money }[] };
};
export type BillsBlock = Block & {
  upcoming: { name: string; due_on: string; days_away: number; amount_kes: Money; short: boolean }[];
  shortfalls: { date: string; short_by_kes: Money; bills: string[]; bills_kes: Money }[];
  lowest: { date: string; balance_kes: Money } | null;
  days: { date: string; expected_sales_kes: Money; left_kes: Money; bills_kes: Money; balance_kes: Money }[];
  opening_kes: Money;
  notes: string[];
};
export type SpikesBlock = Block & { spikes: { name: string; this_month_kes: Money; usual_kes: Money; up_pct: number; extra_kes: Money }[] };
export type SavingsBlock = Block & { captured_kes_month: Money; hours_saved_30d: number; approved_ideas: number };

// ── Sales & Dishes ───────────────────────────────────────────────────────────
export type SevenDayBlock = Block & { days: { date: string; sales: Money; orders: number }[]; total: Money };
export type ForecastBlock = Block & {
  actual: { date: string; sales: Money }[];
  next_7_days: { date: string; day: string; usual: Money; low: Money; high: Money }[];
  unusual_days: { date: string; sales: Money; expected: Money; off_by_pct: number }[];
  note: string;
};
export type MatrixBlock = Block & {
  popular_line_units: number | null;
  earns_line: Money | null;
  dishes: { name: string; kind: string; sold: number; keeps_pct: number; earns_per_plate: Money; profit: Money; trend: string }[];
};
export type DishesByKesBlock = Block & { dishes: { name: string; profit: Money; sold: number; keeps_pct: number }[] };
export type PriceIdeasBlock = Block & {
  ideas: { id: number | null; dish: string; kind: string; from: Money; to: Money; month_gain: Money; why: string }[];
  priced_too_low: { dish: string; keeps_pct: number; month_gain: Money }[];
};
export type DeliveryBlock = Block & {
  channels: { channel: string; orders: number; keeps: Money; keeps_pct: number; pays_commission: boolean }[];
  delivery_gaps: { channel: string; dish: string; commission_pct: number; keeps_pct: number; keeps: Money; keeps_dine_in: Money; price_to_keep_floor: Money }[];
  best_and_weakest_hours: { hours: string; keeps_pct: number; orders: number }[];
};
export type OutlookBlock = Block & { next_30_days: Money; low: Money; high: Money; confidence_pct: number; note: string };
export type WinBackBlock = Block & { lapsed_guests: number; reachable: number; offers: number };
export type InfoBlock = Block & { info: true; how?: string; word?: string; source?: string; reconciled?: boolean; records?: number | null };

// ── Store & Suppliers ────────────────────────────────────────────────────────
export type MissingBlock = Block & {
  window_days: number;
  items: { item: string; unit: string; expected: number; used: number; missing: number; missing_value: Money; off_by_pct: number; check: boolean }[];
};
export type HandoverBlock = Block & { doesnt_match: { item: string; unit: string; store_said: number; kitchen_counted: number; gap: number }[] };
export type ReorderBlock = Block & {
  tracked: number;
  least_cover: { item: string; unit: string; left: number; days_left: number | null }[];
  time_to_reorder: { item: string; unit: string; left: number; status: string }[];
  drafts: { id: number; supplier: string; lines: number }[];
};
export type SuppliersBlock = Block & {
  suppliers: { name: string; on_time_pct: number | null; closed_orders: number; word: string }[];
  overdue_orders: number;
  short_deliveries: { supplier: string; item: string; unit: string; ordered: number; received: number; short_by: number; short_value: Money; on: string }[];
};

// ── Cash Check ───────────────────────────────────────────────────────────────
export type ShiftsBlock = Block & { shifts: { from: string; expected: Money; counted: Money; gap: Money; check: boolean }[] };
export type CancelledBlock = Block & { cancelled_last_7_days: number; unusual_cancelling: number; unusual_refunds: number; late_night_activity: number; to_check: number; note: string };
/** The M-Pesa check (backend/owner/mpesa_match.py): a statement against the M-Pesa sales, over the days the statement covers. */
export type MpesaBlock = Block & {
  source?: string;
  headline?: string;
  window?: { from: string; to: string };
  checked?: { sales: number; payments: number };
  matched?: { count: number; sales: number; kes: Money; receipt: number; exact: number; grouped: number; split: number };
  sales_without_payment?: { count: number; kes: Money; items?: { order_id: number; at: string; kes: Money; what: string }[] };
  payments_without_sale?: { count: number; kes: Money; items?: { receipt: string; at: string; kes: Money; from: string }[] };
  different_amounts?: { order_id: number; receipt: string; sale_kes: Money; payment_kes: Money }[];
  outside_statement?: { sales: number; kes: Money };
  note?: string;
};
export type BelowMenuPriceBlock = Block & { dishes: { dish: string; menu_price: Money; charged: Money; below_pct: number; month_loss: Money }[] };
export type PatternsBlock = Block & {
  patterns: { when: string; weekday: number; shift: "day" | "evening"; times_short: number; of_last: number; short_each: Money; total: Money }[];
  note: string;
};

// ── Staff ────────────────────────────────────────────────────────────────────
export type WagesBlock = Block & {
  wages_pct: number; wages_30d: Money; sales_per_staff_hour: Money; overtime_hours: number; overtime_cost: Money; word: string;
  by_person: { name: string; hours: number; wages: Money }[];
};
export type OnShiftBlock = Block & { scheduled: number; on_shift: number };
export type KitchenBlock = Block & { stations: { station: string; avg_minutes: number }[]; slowest: { station: string; minutes_over_average: number }[] };

// ── Permits & Settings ───────────────────────────────────────────────────────
export type LicencesBlock = Block & { items: { name: string; issuer: string; expires_on: string; days_left: number; status: string; word: string }[] };
export type SettingsBlock = Block & { chosen: boolean; changed: number; total: number; updated_at: string | null };
export type DataTrustBlock = Block & { dishes: number; costs_known_pct: number; missing_costs: number; to_fix: number };

export type { Assumption };
