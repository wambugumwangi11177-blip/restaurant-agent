/**
 * Trading-day sales math, kept for tests.
 *
 * The staff Sales screen does not sum orders. It reads GET /api/v1/sales/today.
 * Orders store money in cents. This helper divides by 100 and keeps paid,
 * non-cancelled orders inside the Nairobi trading day (rolls at 06:00).
 */

export const SERVICE_ROLLOVER_HOUR = 6;
const EAT_MS = 3 * 3600_000;

export type SalesLine = {
  item_name?: string;
  quantity: number;
  unit_price: number;
  menu_item_id?: number;
};

export type SalesOrder = {
  status: string;
  is_paid: boolean;
  total: number;
  created_at: string;
  payment_method?: string;
  order_type?: string;
  delivery_channel?: string;
  items?: SalesLine[];
};

export type HourBar = { hour: number; label: string; kes: number };
export type NamedTotal = { key: string; label: string; count: number; kes: number };

export type TradingSales = {
  day: string;
  start: Date;
  end: Date;
  revenueKes: number;
  orders: number;
  avgKes: number;
  unpaid: number;
  byPayment: NamedTotal[];
  byChannel: NamedTotal[];
  hourly: HourBar[];
  topItems: { name: string; qty: number; kes: number }[];
};

/** A naive timestamp from the API is UTC. One with an offset is already absolute. */
export function toUtcDate(iso: string): Date {
  if (!iso) return new Date(NaN);
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`);
}

export function centsToKes(cents: number | null | undefined): number {
  return (Number(cents) || 0) / 100;
}

function nairobiParts(utc: Date): { year: number; month: number; day: number; hour: number } {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-GB", {
      timeZone: "Africa/Nairobi",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      hourCycle: "h23",
    }).formatToParts(utc).map((p) => [p.type, p.value]),
  );
  return { year: Number(parts.year), month: Number(parts.month), day: Number(parts.day), hour: Number(parts.hour) };
}

/** The open Nairobi service date, YYYY-MM-DD. Before 06:00 the previous calendar day is still open. */
export function tradingDayKey(moment: Date): string {
  const p = nairobiParts(moment);
  const d = new Date(Date.UTC(p.year, p.month - 1, p.day));
  if (p.hour < SERVICE_ROLLOVER_HOUR) d.setUTCDate(d.getUTCDate() - 1);
  const y = d.getUTCFullYear();
  const m = String(d.getUTCMonth() + 1).padStart(2, "0");
  const day = String(d.getUTCDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/** [midnight Nairobi of the trading day, moment). Same window as backend trading_window("today"). */
export function tradingWindow(moment: Date): { start: Date; end: Date; day: string } {
  const day = tradingDayKey(moment);
  const [y, m, d] = day.split("-").map(Number);
  const start = new Date(Date.UTC(y, m - 1, d) - EAT_MS);
  return { start, end: moment, day };
}

export function isPaidSale(order: SalesOrder): boolean {
  return Boolean(order.is_paid) && order.status !== "cancelled";
}

function inWindow(iso: string, start: Date, end: Date): boolean {
  const t = toUtcDate(iso).getTime();
  return t >= start.getTime() && t < end.getTime();
}

function hourLabel(hour: number): string {
  if (hour === 0) return "12a";
  if (hour < 12) return `${hour}a`;
  if (hour === 12) return "12p";
  return `${hour - 12}p`;
}

const PAYMENT_LABEL: Record<string, string> = { cash: "Cash", mpesa: "M-Pesa", card: "Card", pending: "Unpaid" };
const CHANNEL_LABEL: Record<string, string> = {
  dine_in: "Dine in",
  takeout: "Takeaway",
  delivery: "Delivery",
  uber_eats: "Uber Eats",
  bolt_food: "Bolt Food",
  glovo: "Glovo",
  app: "App orders",
};

function bucket(map: Map<string, NamedTotal>, key: string, kes: number) {
  const row = map.get(key) ?? { key, label: PAYMENT_LABEL[key] || CHANNEL_LABEL[key] || key, count: 0, kes: 0 };
  row.count += 1;
  row.kes = Math.round((row.kes + kes) * 100) / 100;
  map.set(key, row);
}

/**
 * Paid, non-cancelled sales inside the open trading day, in shillings.
 * Payment rows, channels, hours and dishes are the same orders, so they add up to revenueKes.
 */
export function tradingSales(orders: SalesOrder[], moment: Date): TradingSales {
  const window = tradingWindow(moment);
  const inDay = orders.filter((o) => inWindow(o.created_at, window.start, window.end) && o.status !== "cancelled");
  const paid = inDay.filter(isPaidSale);
  const revenueKes = Math.round(paid.reduce((sum, o) => sum + centsToKes(o.total), 0) * 100) / 100;
  const payments = new Map<string, NamedTotal>();
  const channels = new Map<string, NamedTotal>();
  const hours = new Map<number, number>();
  const items = new Map<string, { name: string; qty: number; kes: number }>();

  for (const order of paid) {
    const kes = centsToKes(order.total);
    bucket(payments, order.payment_method || "other", kes);
    bucket(channels, order.order_type || "dine_in", kes);
    if (order.order_type === "delivery" && order.delivery_channel) bucket(channels, order.delivery_channel, kes);
    const hour = nairobiParts(toUtcDate(order.created_at)).hour;
    hours.set(hour, (hours.get(hour) || 0) + kes);
    for (const item of order.items || []) {
      const name = item.item_name || `Item ${item.menu_item_id ?? ""}`;
      const row = items.get(name) ?? { name, qty: 0, kes: 0 };
      row.qty += item.quantity || 0;
      row.kes += centsToKes(item.unit_price) * (item.quantity || 0);
      items.set(name, row);
    }
  }

  const hourly = [...hours.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([hour, value]) => ({ hour, label: hourLabel(hour), kes: Math.round(value * 100) / 100 }));

  return {
    day: window.day,
    start: window.start,
    end: window.end,
    revenueKes,
    orders: paid.length,
    avgKes: paid.length ? Math.round((revenueKes / paid.length) * 100) / 100 : 0,
    unpaid: inDay.filter((o) => !o.is_paid).length,
    byPayment: [...payments.values()],
    byChannel: [...channels.values()],
    hourly,
    topItems: [...items.values()].map((i) => ({ ...i, kes: Math.round(i.kes * 100) / 100 })).sort((a, b) => b.kes - a.kes).slice(0, 8),
  };
}

/** True when two shilling totals are the same figure (half a shilling of rounding). */
export function sameKes(a: number, b: number): boolean {
  return Math.abs(a - b) < 0.5;
}
