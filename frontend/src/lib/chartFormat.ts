// Short, readable numbers for chart axes and labels (12.4k, 166k).
export function fmtK(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  const a = Math.abs(n);
  const sign = n < 0 ? "-" : "";
  if (a >= 100_000) return `${sign}${Math.round(a / 1000)}k`;
  if (a >= 1000) return `${sign}${(a / 1000).toFixed(1).replace(/\.0$/, "")}k`;
  return `${sign}${Math.round(a)}`;
}

export function fmtDay(iso: string | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-KE", { day: "numeric", month: "short" });
}

export function fmtWeekday(iso: string | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-KE", { weekday: "short" });
}

/** % change from `before` to `after`, or null if there is nothing to compare against. */
export function pctChange(after: number, before: number): number | null {
  if (!before) return null;
  return Math.round(((after - before) / before) * 1000) / 10;
}
