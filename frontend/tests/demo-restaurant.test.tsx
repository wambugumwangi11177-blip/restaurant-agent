import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import DemoHomePage from "../src/app/demo/page";
import DemoReportsPage from "../src/app/demo/reports/page";
import DemoAreaClient from "../src/components/demo/DemoAreaClient";
import { homeFor } from "@/lib/tenantHome";
import api from "@/lib/api";

const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("@/lib/api", () => ({ default: { get: vi.fn(), post: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("@/context/AuthContext", () => ({
  useAuth: () => ({ user: { restaurant_name: "Demo Restaurant" } }),
}));

const emptyFeed = {
  restaurant_name: "Demo Restaurant",
  period: "today",
  unavailable_metrics: ["kitchen", "waitlist"],
  data_provenance: {
    notice:
      "Recorded directly in this system. Nothing waits on Macsoft or any external data push.",
    latest_order_at: null,
    source_connection: {
      source: "direct",
      state: "direct",
      records: null,
      last_received_at: null,
      reconciled: true,
    },
  },
  revenue: { revenue: 0, orders: 0, avg_order: 0, pace_projection: 0 },
  orders: { orders: 0, active_now: 0, delayed: 0, split: {} },
  kitchen: { avg_prep_min: 0, delay_risk: 0, bottleneck: null },
  stock: { recorded_items: 0, low_stock: [], expiring_48h: [] },
  bookings: { covers_today: 0, next_reservation_min: null, waitlist: 0 },
  staff: { scheduled: 0, on_shift: 0, overtime_risk: 0, labor_cost_pct: 0 },
  attention: [],
  pulse: [],
  performance: { revenue_trend: [] },
  roi: {
    potential_daily: 2910,
    assumption: "Illustrative, not realised savings.",
    opportunities: [],
  },
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.get).mockImplementation(async (url: string) => ({
    data: url.includes("/reports/daily?")
      ? { report_text: "Daily report" }
      : url.includes("/reports/")
        ? {
            period: "daily",
            range: "today",
            revenue: 61200,
            orders: 70,
            top_items: [],
            report_text: "Illustrative daily report",
            coverage_days: 1,
          }
        : url.includes("/areas/")
          ? {
              metrics: [{ label: "Business writes", value: 0 }],
              columns: ["Event", "State"],
              rows: [["Price proposal", "Preview only"]],
              action: "Review evidence.",
              forecast: [],
              trend: [],
            }
          : emptyFeed,
  }));
});
afterEach(cleanup);

it("routes the Demo Restaurant owner to /demo and leaves Vibanda on /vibanda", () => {
  expect(homeFor("Demo Restaurant")).toBe("/demo");
  expect(homeFor(" demo restaurant ")).toBe("/demo");
  expect(homeFor("Vibanda Village")).toBe("/vibanda");
  expect(homeFor("Someone Else")).toBe("/dashboard");
});

it("renders the demo owner home and keeps links inside its own shell", async () => {
  render(<DemoHomePage />);
  expect(await screen.findByText("Today at Demo Restaurant")).toBeTruthy();
  expect(
    screen.getAllByText(/Nothing waits on Macsoft/).length,
  ).toBeGreaterThan(0);
  expect(screen.getByText("No open attention cards")).toBeTruthy();
  expect(screen.queryByText("Waiting for verified restaurant data")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Ask about sales" }));
  expect(push).toHaveBeenCalledWith(
    "/demo/os?q=How%20are%20my%20sales%20today%3F",
  );
  const detailLinks = screen
    .getAllByRole("link", { name: /Open details/ })
    .map((a) => a.getAttribute("href"));
  expect(detailLinks).toContain("/demo/revenue");
  expect(detailLinks.every((href) => href?.startsWith("/demo/"))).toBe(true);
});

it("shows bounded sample report coverage", async () => {
  render(<DemoReportsPage />);
  expect(await screen.findByText(/1 sample days available/)).toBeTruthy();
  expect(await screen.findByText("Illustrative daily report")).toBeTruthy();
  expect(screen.queryByText(/Macsoft is not connected/)).toBeNull();
});

it("area pages load evidence from the demo API", async () => {
  render(
    <DemoAreaClient
      areaKey="audit"
      view={{
        title: "Audit trail",
        description: "Review changes.",
      }}
    />,
  );
  expect(await screen.findByText("Preview only")).toBeTruthy();
  expect(api.get).toHaveBeenCalledWith("/api/v1/demo/areas/audit");
  expect(screen.queryByText("Waiting for verified MacSoft records")).toBeNull();
  expect(
    screen.getByRole("link", { name: /Back to Home/ }).getAttribute("href"),
  ).toBe("/demo");
});
