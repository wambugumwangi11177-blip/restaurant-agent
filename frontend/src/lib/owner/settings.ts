/** The owner's settings as the sheet reads them (GET /owner/settings, PUT /owner/settings, POST /owner/settings/preview). */
export type SettingField = {
  key: string;
  group: string;
  label: string;
  question: string;
  unit: string;
  value: number;
  default: number;
  min: number;
  max: number;
  step: number;
  hint: string;
  is_default: boolean;
};

export type SettingsPayload = { chosen: boolean; updated_at: string | null; updated_by: number | null; fields: SettingField[] };

/** What saving a change would do to Home's ranked cards, worked out with the real engines and rolled back. */
export type SettingsPreview = {
  changes: { key: string; label: string; unit: string; from: number; to: number }[];
  cards_now: number;
  cards_after: number;
  appear: string[];
  disappear: string[];
  figures: string[];
  changed: number;
};

/** "40%" · "KES 200" · "0.7 × average" · "14 days": a value in the unit its setting is asked in. */
export function formatSetting(field: Pick<SettingField, "unit">, value: number): string {
  const n = Number(Number(value).toFixed(2));
  const unit = field.unit;
  if (!unit) return String(n);
  if (unit === "%") return `${n}%`;
  if (unit === "KES") return `KES ${n.toLocaleString("en-KE")}`;
  return `${n} ${unit}`;
}

/** The six questions a new owner is asked first (onboarding "Your targets"), in the order they are asked. */
export const HEADLINE_SETTINGS = [
  "food_cost_target_pct",
  "labour_target_pct",
  "margin_floor_pct",
  "cash_tolerance_kes",
  "missing_stock_flag_pct",
  "expense_spike_pct",
] as const;
