// Owner-readable formatting — single source of truth for the Restaurant OS.
const kes = new Intl.NumberFormat("en-KE", { style: "currency", currency: "KES", maximumFractionDigits: 0 });

export const fmtKes = (n: number) => kes.format(n || 0);
export const fmtPct = (n: number) => `${(n || 0).toFixed(1)}%`;

export function greetingFor(hour: number): string {
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}
export const greetingNow = () => greetingFor(new Date().getHours());

export const fmtDate = () =>
  new Date().toLocaleDateString("en-KE", { weekday: "long", day: "numeric", month: "long" });