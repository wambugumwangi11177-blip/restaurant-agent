import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import HomePage from "../src/app/vibanda/page";
import api from "@/lib/api";

const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("@/lib/api", () => ({ default: { get: vi.fn(), post: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => ({ user: { restaurant_name: "Vibanda" } }) }));

const feed = {
  restaurant_name: "Vibanda Village", period: "today", unavailable_metrics: ["kitchen", "waitlist"],
  revenue: { revenue: 500, orders: 1, avg_order: 500, pace_projection: 0 },
  orders: { orders: 1, active_now: 0, delayed: 0, split: { dine_in: 1 } },
  kitchen: { avg_prep_min: 0, delay_risk: 0, bottleneck: null },
  stock: { low_stock: [], expiring_48h: [] },
  bookings: { covers_today: 0, next_reservation_min: null, waitlist: 0 },
  staff: { scheduled: 0, on_shift: 0, overtime_risk: 0, labor_cost_pct: 0 },
  attention: [{ id: "stock-1", domain: "Stock", title: "Review beef stock", why: "Below threshold",
    what_to_do: "Check quantity", impact: "", status: "open" }],
  pulse: [], performance: { revenue_trend: [] },
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.get).mockImplementation(async (url) => ({ data: url.includes("reports") ? { report_text: "Daily report" } : feed }));
});
afterEach(cleanup);

it("shows missing kitchen data honestly and only navigates through the explicit Ask button", async () => {
  render(<HomePage />);
  await screen.findByText("Not available");
  expect(screen.queryByText("On pace")).toBeNull();
  expect(screen.queryByText("No delays reported")).toBeNull();
  expect(screen.queryByText("No sales in this period yet")).toBeNull();
  fireEvent.click(screen.getByText("Revenue"));
  expect(push).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Ask about sales" }));
  expect(push).toHaveBeenCalledWith("/vibanda/os?q=How%20are%20my%20sales%20today%3F");
});

it("keeps the attention card and shows an error when a decision fails", async () => {
  vi.mocked(api.post).mockRejectedValue(new Error("offline"));
  render(<HomePage />);
  await screen.findByText("Review beef stock");
  fireEvent.click(screen.getByRole("button", { name: "Approve" }));
  expect((await screen.findByRole("alert")).textContent).toContain("could not be saved");
  expect(screen.getByText("Review beef stock")).toBeTruthy();
});
