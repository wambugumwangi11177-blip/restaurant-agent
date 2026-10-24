/** The same sums as backend/owner/menu_math.py, in cents, with no model call. */

export function targetPriceCents(costCents: number, marginPct: number, stepCents: number): number {
  if (costCents < 0) throw new Error("a cost cannot be negative");
  if (!(marginPct >= 0 && marginPct < 95)) throw new Error("the share to keep must be at least 0% and below 95%");
  if (stepCents < 1) throw new Error("a price step is at least one cent");
  const exact = (costCents * 10000) / ((100 - marginPct) * 100);
  return Math.ceil(exact / stepCents - 1e-9) * stepCents;
}

export function monthGainCents(priceFromCents: number, priceToCents: number, platesAMonth: number): number {
  if (platesAMonth < 0) throw new Error("plates cannot be negative");
  return (priceToCents - priceFromCents) * platesAMonth;
}
