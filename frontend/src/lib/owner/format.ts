/**
 * Owner-facing formatting (docs/v2/SPEC.md §0.3, §3.4): shillings are written "KES 412,000", owner time is Nairobi (UTC+3)
 * wherever the browser happens to be, and a data state is always said in words.
 */
import type { Block, BlockState } from "./types";

const TZ = "Africa/Nairobi";
const GROUP = new Intl.NumberFormat("en-KE", { maximumFractionDigits: 0 });
const GROUP_CENTS = new Intl.NumberFormat("en-KE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** KES 412,000 · -KES 1,200 · whole shillings unless `cents` (an accountant's figure). null/undefined → "—" is never produced here. */
export function kes(value: number | null | undefined, opts: { cents?: boolean } = {}): string {
  const n = Number.isFinite(value as number) ? (value as number) : 0;
  const body = opts.cents ? GROUP_CENTS.format(Math.abs(n)) : GROUP.format(Math.abs(Math.round(n)));
  return `${n < 0 && Math.round(n) !== 0 ? "-" : ""}KES ${body}`;
}

/** KES 12.4k / KES 1.2M for tight spaces (chart labels). */
export function kesShort(value: number): string {
  const n = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  if (n >= 1_000_000) return `${sign}KES ${(n / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
  if (n >= 10_000) return `${sign}KES ${Math.round(n / 1000)}k`;
  if (n >= 1_000) return `${sign}KES ${(n / 1000).toFixed(1).replace(/\.0$/, "")}k`;
  return `${sign}KES ${Math.round(n)}`;
}

/** 29.3% — one decimal, a trailing .0 is dropped. */
export function pct(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "0%";
  return `${value.toFixed(1).replace(/\.0$/, "")}%`;
}

/** "+14.8%" / "-3.2%" — a change against the same weekday last week. */
export function signedPct(value: number): string {
  return `${value > 0 ? "+" : value < 0 ? "-" : ""}${Math.abs(value).toFixed(1).replace(/\.0$/, "")}%`;
}

/** The last twelve calendar months, newest first, as the owner API takes them (2026-10) and says them (October 2026). */
export function lastMonths(now: Date = new Date(), count = 12): { value: string; label: string }[] {
  const nairobi = new Date(now.getTime() + 3 * 3600_000);
  return Array.from({ length: count }, (_, i) => {
    const d = new Date(Date.UTC(nairobi.getUTCFullYear(), nairobi.getUTCMonth() - i, 1));
    return {
      value: `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`,
      label: new Intl.DateTimeFormat("en-KE", { timeZone: "UTC", month: "long", year: "numeric" }).format(d),
    };
  });
}
export function plural(
n: number, one: string, many = `${one}s`): string {
  return `${n.toLocaleString("en-KE")} ${n === 1 ? one : many}`;
}

/** The server's ISO timestamps carry an explicit offset; a naive one is UTC. */
export function toDate(iso: string): Date {
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`);
}

export function nairobiHour(now: Date = new Date()): number {
  return Number(new Intl.DateTimeFormat("en-GB", { timeZone: TZ, hour: "2-digit", hourCycle: "h23" }).format(now));
}

export function greeting(now: Date = new Date()): string {
  const h = nairobiHour(now);
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

/** "Thursday 15 October" in Nairobi — the calendar date, not the open service. */
export function nairobiDate(now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-KE", { timeZone: TZ, weekday: "long", day: "numeric", month: "long" }).format(now);
}

const SERVICE_ROLLOVER_HOUR = 6;

function nairobiYmd(now: Date): { year: number; month: number; day: number; hour: number } {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", hourCycle: "h23",
  }).formatToParts(now);
  const num = (type: string) => Number(parts.find((p) => p.type === type)?.value);
  return { year: num("year"), month: num("month"), day: num("day"), hour: num("hour") };
}

/**
 * The trading day the open-service figures belong to.
 * Before 06:00 Nairobi: "Fri 23 Oct service, still open". After: "Sat 24 Oct service".
 */
export function serviceCaption(now: Date = new Date()): string {
  const p = nairobiYmd(now);
  let year = p.year;
  let month = p.month;
  let day = p.day;
  const stillOpen = p.hour < SERVICE_ROLLOVER_HOUR;
  if (stillOpen) {
    const prev = new Date(Date.UTC(year, month - 1, day) - 86_400_000);
    year = prev.getUTCFullYear();
    month = prev.getUTCMonth() + 1;
    day = prev.getUTCDate();
  }
  const iso = `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
  const name = `${weekday(iso)} ${shortDay(iso)} service`;
  return stillOpen ? `${name}, still open` : name;
}

/** "3:40 pm" in Nairobi. */
export function nairobiTime(iso: string): string {
  return new Intl.DateTimeFormat("en-KE", { timeZone: TZ, hour: "numeric", minute: "2-digit", hour12: true }).format(toDate(iso)).replace(/\s?(am|pm)/i, (m) => ` ${m.trim().toLowerCase()}`);
}

/** "14 Oct" for a Nairobi calendar day written YYYY-MM-DD. */
export function shortDay(day: string): string {
  const [y, m, d] = day.split("-").map(Number);
  return new Intl.DateTimeFormat("en-KE", { timeZone: "UTC", day: "numeric", month: "short" }).format(new Date(Date.UTC(y, m - 1, d)));
}

/** "Wed" for a Nairobi calendar day. */
export function weekday(day: string): string {
  const [y, m, d] = day.split("-").map(Number);
  return new Intl.DateTimeFormat("en-KE", { timeZone: "UTC", weekday: "short" }).format(new Date(Date.UTC(y, m - 1, d)));
}

/** "just now" · "12 min ago" · "3 h ago" · "2 days ago". */
export function ago(iso: string, now: Date = new Date()): string {
  const minutes = Math.max(0, Math.round((now.getTime() - toDate(iso).getTime()) / 60000));
  if (minutes < 2) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  return `${days} ${days === 1 ? "day" : "days"} ago`;
}

export type Tone = "good" | "info" | "warn" | "bad" | "quiet";

/** Every data state, said in words an owner uses. `block` supplies the fields a state carries (day/of, entered_up_to, as_of). */
export function stateWords(block: Pick<Block, "state"> & Partial<Block>, now: Date = new Date()): { word: string; tone: Tone; detail?: string } {
  const state: BlockState = block.state;
  switch (state) {
    case "live":
      return { word: "Live", tone: "good", detail: block.as_of ? `as of ${nairobiTime(block.as_of)}` : undefined };
    case "as_entered":
      return { word: block.entered_up_to ? `As entered up to ${shortDay(block.entered_up_to)}` : "As entered", tone: "info" };
    case "learning":
      return { word: block.day != null && block.of != null ? `Learning · day ${block.day} of ${block.of}` : "Still learning", tone: "quiet" };
    case "not_from_pos":
      return { word: block.source ? `From your ${block.source}` : "Not from the till", tone: "info" };
    case "stale":
      return { word: block.age_days != null ? `Out of date · ${plural(block.age_days, "day")} old` : "Out of date", tone: "warn", detail: block.as_of ? ago(block.as_of, now) : undefined };
    case "no_data":
      return { word: "Nothing recorded yet", tone: "quiet" };
    case "unavailable":
      return { word: "Not available", tone: "quiet" };
  }
}
