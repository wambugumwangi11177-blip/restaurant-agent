export function formatKes(amount: number | null | undefined, { compact = false } = {}): string {
  if (amount == null || Number.isNaN(amount)) return "—";
  if (compact && amount >= 100_000) return `${Math.round(amount).toLocaleString("en-KE")} KES`;
  return `${amount.toLocaleString("en-KE", { maximumFractionDigits: amount < 1000 ? 2 : 0 })} KES`;
}