import { describe, expect, it } from "vitest";
import { centsToKes, sameKes, tradingDayKey, tradingSales, type SalesOrder } from "@/lib/salesFigures";

/** Friday 23 Oct 2026, 20:00 Nairobi = 17:00 UTC. */
const FRIDAY_EVENING = "2026-10-23T17:00:00";
/** Saturday 24 Oct 2026, 01:30 Nairobi = Friday 22:30 UTC. The Friday service is still open. */
const SATURDAY_0130 = new Date("2026-10-23T22:30:00Z");
/** Saturday 24 Oct 2026, 14:00 Nairobi = 11:00 UTC. Saturday's service. */
const SATURDAY_1400 = new Date("2026-10-24T11:00:00Z");
const SATURDAY_LUNCH = "2026-10-24T09:00:00";

function order(partial: Partial<SalesOrder> & Pick<SalesOrder, "total" | "created_at">): SalesOrder {
  return {
    status: "served",
    is_paid: true,
    payment_method: "cash",
    order_type: "dine_in",
    items: [],
    ...partial,
  };
}

describe("cents become shillings once", () => {
  it("1,634,000 cents is KES 16,340, and a line priced in cents is too", () => {
    expect(centsToKes(1_634_000)).toBe(16_340);
    const figures = tradingSales([
      order({
        total: 1_634_000,
        created_at: SATURDAY_LUNCH,
        items: [{ item_name: "Beef fry", quantity: 1, unit_price: 450_000 }],
      }),
    ], SATURDAY_1400);
    expect(figures.revenueKes).toBe(16_340);
    expect(figures.topItems[0]).toMatchObject({ name: "Beef fry", kes: 4_500 });
    expect(figures.byPayment.reduce((s, r) => s + r.kes, 0)).toBe(16_340);
  });
});

describe("one trading day, the same paid total everywhere", () => {
  const orders = [
    order({ total: 1_000_000, created_at: FRIDAY_EVENING, payment_method: "mpesa", order_type: "dine_in" }),
    order({ total: 634_000, created_at: FRIDAY_EVENING, payment_method: "cash", order_type: "takeout" }),
    order({ total: 200_000, created_at: FRIDAY_EVENING, is_paid: false, payment_method: "pending" }),
    order({ total: 500_000, created_at: FRIDAY_EVENING, status: "cancelled", is_paid: true }),
    order({ total: 300_000, created_at: SATURDAY_LUNCH, payment_method: "card" }),
  ];

  it("at 01:30 Nairobi the open day is still Friday and only its paid sales count", () => {
    expect(tradingDayKey(SATURDAY_0130)).toBe("2026-10-23");
    const figures = tradingSales(orders, SATURDAY_0130);
    expect(figures.revenueKes).toBe(16_340);
    expect(figures.orders).toBe(2);
    expect(figures.unpaid).toBe(1);
    expect(figures.avgKes).toBe(8_170);
    expect(sameKes(figures.revenueKes, figures.byPayment.reduce((s, r) => s + r.kes, 0))).toBe(true);
    expect(figures.hourly.every((h) => h.kes > 0)).toBe(true);
    expect(figures.hourly.map((h) => h.hour)).toContain(20);
  });

  it("at 14:00 Nairobi Friday's service has closed and Saturday's lunch is the total", () => {
    expect(tradingDayKey(SATURDAY_1400)).toBe("2026-10-24");
    const figures = tradingSales(orders, SATURDAY_1400);
    expect(figures.revenueKes).toBe(3_000);
    expect(figures.orders).toBe(1);
    expect(figures.byPayment.map((p) => p.key)).toEqual(["card"]);
  });
});
