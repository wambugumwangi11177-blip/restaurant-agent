/**
 * Ask LEVIII's answers as the shell reads them (backend/owner/answers.py, docs/v2/SPEC.md §4 P5.1): one shape for the five forms.
 * The sentence (`headline`) is written by code from the numbers in `rows`, `drivers` and `columns`; the screen shows both.
 */
import { kes, pct } from "./format";
import type { BlockState, Insight } from "./types";

export type AskForm = "what" | "why" | "what_if" | "what_to_do" | "compare";

export type AnswerUnit = "kes" | "pct" | "pct_points" | "count" | "hours" | "kg" | "text";

export type AnswerRow = {
  key: string;
  label: string;
  value: number | null;
  unit: AnswerUnit;
  note?: string;
  /** a "what should I do" idea */
  id?: string;
  action?: string;
  why?: string | null;
  tier?: "now" | "loss" | "idea";
  domain?: string;
};

export type Driver = { key: string; label: string; found: boolean; value: number | null; unit: AnswerUnit; note: string };

/** One side of a comparison: a branch, or a period. */
export type Column = {
  name?: string;
  key?: string;
  label?: string;
  from?: string;
  to?: string;
  days?: number;
  sales: number;
  orders: number;
  average_order?: number | null;
  food_cost_pct: number | null;
  wages_pct?: number | null;
  food_cost_word?: string | null;
};

export type AnswerAssumption = { text: string; setting?: string; value?: number | string };

export type OwnerAnswer = {
  question: string;
  form: AskForm;
  topic: string;
  topic_label: string;
  state: BlockState;
  as_of: string | null;
  headline: string;
  insight?: Insight | null;
  reason?: string;
  rows: AnswerRow[];
  assumptions: AnswerAssumption[];
  next: string[];
  conversation_id?: number;
  // why
  day?: string;
  weekday?: string;
  drivers?: Driver[];
  // what if
  verdict?: string;
  dish?: string;
  // what should I do
  goal_kes?: number | null;
  covered_by?: number | null;
  total_kes?: number | null;
  // compare
  kind?: "branches" | "periods";
  columns?: Column[];
};

export const ASK_FORMS: { id: AskForm; label: string; hint: string; examples: string[] }[] = [
  { id: "what", label: "What", hint: "Where things stand", examples: ["Am I making a profit this month?", "How is my cash count looking?", "Do my M-Pesa payments match my sales?", "How are my suppliers doing?", "What will run out soon?", "Which dishes earn the most?", "Which guests haven't come back?"] },
  { id: "why", label: "Why", hint: "What lay behind a day", examples: ["Why were sales down yesterday?", "Why was Tuesday last week bad?", "What happened to sales on Friday?"] },
  { id: "what_if", label: "What if", hint: "Try a price before you change it", examples: ["What if I raise the price of my best seller?", "What if I cut Burger by 10%?"] },
  { id: "what_to_do", label: "What should I do", hint: "The biggest wins, in KES", examples: ["What should I do to make more money?", "How can I find KES 20,000 more a month?"] },
  { id: "compare", label: "Compare", hint: "Branches, or this week against last", examples: ["Compare my branches", "This week vs last week", "This month vs last month"] },
];

/** How a row's number is written: "KES 1,899", "37%", "7.8 points", "12 hours". A row with no number (a note) has none. */
export function rowValue(row: Pick<AnswerRow, "value" | "unit">): string {
  if (row.value == null || row.unit === "text") return "";
  switch (row.unit) {
    case "kes": return kes(row.value);
    case "pct": return pct(row.value);
    case "pct_points": return `${row.value.toFixed(1).replace(/\.0$/, "")} points`;
    case "hours": return `${row.value.toLocaleString("en-KE", { maximumFractionDigits: 1 })} hours`;
    case "kg": return `${row.value.toLocaleString("en-KE", { maximumFractionDigits: 1 })} kg`;
    default: return row.value.toLocaleString("en-KE");
  }
}

// What the owner asks for help with rather than about their restaurant: these go to the writing assistant (/ai/chat), not to the five forms.
const GUIDANCE = [
  /how can this software/, /what can this software/, /what can you do/, /how does this work/, /explain this feature/, /show me how this software/,
  /\bhelp me\b/, /\bcan you help\b/, /\bcould you help\b/, /\bbrainstorm\b/, /\bcreative\b/, /\bgive me ideas\b/, /\bany ideas\b/, /\bsuggest\b/,
  /\btips for\b/, /\bways to\b/, /\bgood way to\b/, /\bbest way to\b/, /\bi want to change\b/, /\bredesign\b/, /\bprepare for connecting\b/, /\bplan for\b/, /\bideas for\b/,
];

/** A request for help or an explanation of the software, as opposed to a question about the owner's own figures. */
export function isGuidance(question: string): boolean {
  const q = question.toLowerCase();
  return GUIDANCE.some((re) => re.test(q));
}

// Precise data questions stay on the five forms. Open-ended advice does not.
const PRECISE = [
  /\b(sales|revenue|profit|orders|cash|mpesa|m-pesa|stock|supplier|guest|price|priced|sold|sell)\b/,
  /\b(why|what if|compare)\b/,
  /\bwhat should i do\b/,
  /\bhow (?:can|do|could|should) i\b/,
  /\bkes\b|\bksh\b/,
  /\bwho should i\b/,
];
const OPEN_ENDED = [
  /\badvice\b/, /\brecommend/, /\bwhat do you think\b/, /\bhow would you\b/, /\bcome up with\b/,
  /\bi(?:'m| am) stuck\b/, /\bhelp me think\b/, /\bwhat are (?:some|a few) (?:ways|ideas|options)\b/,
  /\bshould we\b/, /\bideas\b/,
];

/** Typed text that should go to the writing assistant. Precise sales and number questions stay deterministic. */
export function prefersChat(question: string): boolean {
  if (isGuidance(question)) return true;
  const q = question.toLowerCase();
  if (PRECISE.some((re) => re.test(q))) return false;
  return OPEN_ENDED.some((re) => re.test(q));
}

/** A saved assistant message that is one of our answers (it has a form), as opposed to an older chat reply. */
export function asOwnerAnswer(value: unknown): OwnerAnswer | null {
  if (!value || typeof value !== "object") return null;
  const v = value as Partial<OwnerAnswer>;
  return typeof v.form === "string" && typeof v.headline === "string" && Array.isArray(v.rows) ? (v as OwnerAnswer) : null;
}
