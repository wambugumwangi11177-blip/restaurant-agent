import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import DemoAreaClient from "../src/components/demo/DemoAreaClient";
import DemoOwnerInsights from "../src/components/demo/DemoOwnerInsights";
import { RecordsTable, ValueChart } from "../src/components/demo/DemoDataViews";
import { cell, DEMO_MODULES } from "@/lib/demo-modules";
import { VIBANDA_AREA_SECTIONS } from "@/lib/vibandaAreas";
import api from "@/lib/api";
vi.mock("@/lib/api", () => ({ default: { get: vi.fn() } }));
vi.mock("../src/components/demo/DemoForecast", () => ({ default: () => null }));
const view = {
  title: "Orders",
  description: "Recorded orders",
  source: "Orders",
  metrics: [],
  mode: "trend" as const,
  visual: "Order volume",
  table: "Recent orders",
  note: "",
};
const feed = {
  period: "today",
  performance: {
    revenue_trend: [{ date: "2026-09-29", revenue: 1000, orders: 2 }],
  },
  orders: { split: { dine_in: 2 } },
  stock: { recorded_items: 0, low_stock: [] },
};
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.get).mockResolvedValue({ data: {} });
});
afterEach(cleanup);
it("renders returned order records and converts cents exactly once", async () => {
  vi.mocked(api.get).mockResolvedValue({
    data: [
      {
        id: 12,
        created_at: "2026-09-29T09:00:00",
        status: "ready",
        order_type: "delivery",
        total: 150000,
        is_paid: true,
      },
    ],
  });
  render(<DemoAreaClient areaKey="orders" view={view} />);
  expect(
    await screen.findByRole("cell", { name: /Ksh\s+1,500/i }),
  ).toBeTruthy();
  expect(screen.getByRole("cell", { name: "ready" })).toBeTruthy();
  expect(api.get).toHaveBeenCalledWith("/api/v1/orders/", { timeout: 20000 });
  expect(screen.queryByText(/No records yet/)).toBeNull();
});
it("distinguishes failed records from an empty response and retries", async () => {
  vi.mocked(api.get)
    .mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValueOnce({ data: [] });
  render(<DemoAreaClient areaKey="orders" view={view} />);
  expect((await screen.findByRole("alert")).textContent).toContain(
    "does not mean there are no records",
  );
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByText("No orders have been recorded.")).toBeTruthy();
});
it("rejects an HTTP-success response carrying an analysis error", async () => {
  vi.mocked(api.get).mockResolvedValue({
    data: { available: false, error: "failed" },
  });
  render(<DemoAreaClient areaKey="menu" view={{ ...view, title: "Menu" }} />);
  expect(await screen.findByRole("alert")).toBeTruthy();
  expect(screen.queryByText(DEMO_MODULES.menu.empty)).toBeNull();
});
it("does not present a missing item cost as a profitable menu item", async () => {
  vi.mocked(api.get).mockResolvedValue({
    data: {
      matrix: [
        {
          name: "Stew",
          price: 50000,
          cost_price: 0,
          margin_pct: 100,
          qty_sold: 0,
          classification: "Star",
        },
      ],
    },
  });
  render(<DemoAreaClient areaKey="menu" view={view} />);
  expect(
    await screen.findByRole("cell", { name: "Verify item cost" }),
  ).toBeTruthy();
  expect(screen.getByRole("cell", { name: "No recorded sales" })).toBeTruthy();
  expect(screen.queryByRole("cell", { name: "100%" })).toBeNull();
});
it("paginates supporting records without hiding the record count", () => {
  render(
    <RecordsTable
      rows={Array.from({ length: 11 }, (_, id) => ({ id }))}
      columns={[{ key: "id", label: "Order" }]}
      caption="Recorded orders"
      empty="Empty"
    />,
  );
  expect(screen.getByText("1–10 of 11")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Next" }));
  expect(screen.getByText("11–11 of 11")).toBeTruthy();
  expect(screen.getByRole("cell", { name: "10" })).toBeTruthy();
});
it("labels counts without currency and never invents bars for all-zero history", () => {
  const { rerender } = render(
    <ValueChart
      rows={[{ label: "Monday", count: 3 }]}
      labelKey="label"
      valueKey="count"
      title="Orders"
      format="count"
    />,
  );
  expect(screen.getByRole("img").getAttribute("aria-label")).toBe(
    "Orders: Monday 3",
  );
  rerender(
    <ValueChart
      rows={[{ label: "Monday", count: 0 }]}
      labelKey="label"
      valueKey="count"
      title="Orders"
      format="count"
    />,
  );
  expect(screen.queryByRole("img")).toBeNull();
});
it("keeps owner evidence usable when one specialist fails and hides unsafe margin totals", async () => {
  vi.mocked(api.get).mockImplementation(async (url) => {
    if (url.includes("supply-chain")) throw new Error("offline");
    if (url.includes("data-quality"))
      return { data: { summary: { total_items: 1, items_with_issues: 1 } } };
    if (url.includes("profit"))
      return {
        data: {
          summary: {
            total_orders_30d: 10,
            gross_margin_pct: 100,
            total_gross_profit_30d: 500000,
          },
        },
      };
    return { data: {} };
  });
  render(<DemoOwnerInsights feed={feed} />);
  expect(
    await screen.findByText(
      "Verify menu costs before relying on a margin figure.",
    ),
  ).toBeTruthy();
  expect(screen.getByRole("img", { name: /Daily paid revenue/ })).toBeTruthy();
  expect(
    screen.getByRole("img", { name: /Daily paid orders:.*2/ }),
  ).toBeTruthy();
  expect(screen.queryByText("100%")).toBeNull();
  expect(await screen.findByRole("alert")).toBeTruthy();
  for (const [, , slug] of VIBANDA_AREA_SECTIONS.flatMap((s) => s.areas))
    expect(
      screen
        .getAllByRole("link")
        .some((l) => l.getAttribute("href") === `/demo/${slug}`),
    ).toBe(true);
});
it("displays approved pricing impact as projected, without a realized-savings total", async () => {
  vi.mocked(api.get).mockImplementation(async (url) => ({
    data: url.includes("/roi")
      ? {
          time_saved: { hours_saved_30d: 4 },
          money_captured: {
            recommendations_approved: 2,
            monthly_impact_cents: 200000,
          },
          opportunities: [
            { label: "Review dish cost", monthly_value_cents: 100000 },
          ],
        }
      : {},
  }));
  render(<DemoOwnerInsights feed={feed} />);
  expect(
    await screen.findByText(/Projected monthly impact: Ksh\s+2,000/i),
  ).toBeTruthy();
  expect(
    screen.getByText(/Approval does not verify realized profit/),
  ).toBeTruthy();
});
it("formats timestamps in Nairobi and never displays objects as raw JSON", () => {
  expect(cell("2026-09-29T09:00:00", "date")).toContain("12:00");
  expect(cell({ token: "hidden" })).toBe("—");
  expect(cell(150000, "cents")).toMatch(/Ksh\s+1,500/i);
});
