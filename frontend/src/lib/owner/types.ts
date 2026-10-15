/**
 * The owner API's payload as the shell reads it (backend/owner/*, docs/v2/SPEC.md §3.1). Every block is
 * `{ state, as_of, [assumption], …fields }`; the fields below are the ones the screens use.
 */
export type BlockState = "live" | "as_entered" | "learning" | "not_from_pos" | "stale" | "no_data" | "unavailable";

export type Assumption = { setting: string; value: number; label?: string };

export type Block = {
  state: BlockState;
  as_of: string | null;
  reason?: string | null;
  assumption?: Assumption;
  assumptions?: Assumption[];
  entered_up_to?: string;
  day?: number;
  of?: number;
  age_days?: number;
  source?: string;
  /** Fields that only some blocks carry; `unknown` keeps them honest until a component narrows them. */
  [field: string]: unknown;
};

export type Freshness = {
  latest_sale_at: string | null;
  data_age_days: number | null;
  is_stale: boolean;
  source: string;
  source_state: string;
  source_reconciled: boolean;
  source_trusted: boolean;
  source_notice: string;
  source_records: number | null;
  source_last_received_at: string | null;
};

export type TrendDay = { date: string; sales: number; orders: number };

export type BreakEven = Block & {
  break_even_kes: number;
  sales_today_kes: number;
  to_go_kes: number;
  covered: boolean;
  crossed_at: string | null;
  fixed_per_day_kes: number;
  food_cost_pct: number;
  note: string;
  built_from: { label: string; period: string; days: number; fixed_costs_kes: number; wages_kes: number; lines: { name: string; kes: number }[] };
};

export type Pulse = Block & {
  sales_today: number;
  orders_today: number;
  vs_same_weekday_pct: number | null;
  vs_same_weekday_state: BlockState;
  sales_in_period: number;
  orders_in_period: number;
  trend_7d: TrendDay[];
  breakeven_at: BreakEven;
  money_match: { cash: Block & { checked?: number; to_check?: number }; mpesa: Block };
  freshness: Freshness;
};

export type DecisionCard = {
  id: string;
  domain: string;
  sentence: string;
  kes_month: number | null;
  action: string;
  why: string;
  assumption: Assumption | null;
  decision: { options: string[] } | null;
};

export type CostingYouMoney = Block & { cards: DecisionCard[]; more: number; ranking: string };

export type HealthStatus = "good" | "watch" | "bad" | "unknown";
export type HealthTile = { area: AreaKey; title: string; number: number | null; unit: string; word: string; status: HealthStatus; label: string };
export type Health = Block & { tiles: HealthTile[] };

export const AREA_KEYS = ["money", "sales_dishes", "store", "cash", "staff", "permits"] as const;
export type AreaKey = (typeof AREA_KEYS)[number];

export type AreaSummary = { number: number | null; unit: string; word: string; status: HealthStatus; label: string };
export type Area = {
  key: AreaKey;
  title: string;
  state: BlockState;
  as_of: string | null;
  summary: AreaSummary;
  blocks: Record<string, Block>;
};

export type ComingUp = {
  bills: Block & { items?: { name: string; due_on: string; days_away: number; amount_kes: number; short: boolean }[] };
  licences: Block & { items?: { name: string; issuer: string; expires_on: string; days_left: number; status: string; word: string }[] };
  deliveries: Block & { items?: { item: string; supplier: string; expected_at: string; status: string }[] };
  bookings: Block & { covers_today?: number; next_days?: { date: string; bookings: number; covers: number }[] };
};

export type OwnerHome = {
  restaurant: { id: number; name: string };
  period: "today" | "7d" | "30d";
  timezone: string;
  generated_at: string;
  pulse: Pulse;
  costing_you_money: CostingYouMoney;
  health: Health;
  areas: Record<AreaKey, Area>;
  coming_up: ComingUp;
  read: Block & { text: string | null };
};
