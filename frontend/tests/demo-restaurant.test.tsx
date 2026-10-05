import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import DemoHomePage from "../src/app/demo/page";
import DemoReportsPage from "../src/app/demo/reports/page";
import DemoOS from "../src/app/demo/os/page";
import DemoAreaClient from "../src/components/demo/DemoAreaClient";
import { homeFor } from "@/lib/tenantHome";
import api from "@/lib/api";
import { RETRY } from "@/lib/retry";

const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("@/lib/api", () => ({ default: { get: vi.fn(), post: vi.fn() } }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock("@/context/AuthContext", () => ({
  useAuth: () => ({ user: { restaurant_name: "Demo Restaurant" } }),
}));

const emptyFeed = {
  restaurant_name: "Demo Restaurant",
  period: "today",
  unavailable_metrics: ["kitchen", "waitlist"],
  data_provenance: {
    notice: "Recorded directly in this system. Nothing waits on Macsoft or any external data push.",
    latest_order_at: null,
    source_connection: { source: "direct", state: "direct", records: null, last_received_at: null, reconciled: true },
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
};

const sampleReport = {
  period: "daily",
  range: "2026-09-30 – 2026-09-30",
  revenue: 61200,
  orders: 70,
  coverage_days: 1,
  headline: "Today (Wednesday) the restaurant took KES 61,200 from 70 orders.",
  kpis: [
    { label: "Sales", value: "KES 61,200" },
    { label: "Orders", value: "70" },
    { label: "Average order", value: "KES 874" },
    { label: "Kept after ingredients", value: "KES 37,760" },
  ],
  comparison: { label: "last Wednesday", previous_revenue: 57528, change_pct: 6.4 },
  series: [
    { date: "2026-09-29", day: "Tue", revenue: 54394, orders: 60 },
    { date: "2026-09-30", day: "Wed", revenue: 61200, orders: 70 },
  ],
  weekday_pattern: [
    { day: "Mon", revenue: 50000 },
    { day: "Sat", revenue: 80000 },
  ],
  channels: [
    { label: "Dine-in", value: 45 },
    { label: "Takeaway", value: 18 },
    { label: "Delivery", value: 7 },
  ],
  dishes: [{ name: "Beef pilau", price: 650, cost: 270, units: 24, sales: 15600, contribution: 9120, margin_pct: 58 }],
  story: [{ title: "Stock and waste", text: "Beef is down to 2 days of cover, so order today." }],
  decisions: [{ idea: "Use vegetables before expiry", why: "8 kg can be used before expiry.", next_step: "Feature the vegetable bowl.", expected: "KES 1,440 potential / day" }],
  money_today: { sales: 61200, food_cost: 23440, contribution: 37760, labor: 10500, other: 6500, surplus: 20760 },
  note: "",
};

const stockArea = {
  key: "stock",
  title: "Stock",
  subtitle: "What is on the shelf, and what to order.",
  headline: "You track 13 ingredients, all used by the dishes on your menu.",
  how_to_read: "Days of cover is how long the stock lasts at today's selling rate.",
  metrics: [{ label: "Need ordering", value: 1 }],
  columns: ["Ingredient", "On hand"],
  rows: [["Beef", "6 kg"]],
  table_title: "Everything on the shelf",
  table_note: "Used per day is worked out from the recipes.",
  action: "Order beef.",
  attention: [{ id: "beef-low", title: "Beef is running low", why: "It covers 2 days.", what_to_do: "Order beef today.", level: "urgent", impact: "Protects Beef pilau sales" }],
  decisions: [{ idea: "Order beef today", why: "Beef pilau uses it all.", next_step: "Place the order now.", expected: "Avoids running out" }],
  charts: [{ type: "meters", title: "How many days each ingredient will last", unit: "days", target: 2, items: [{ label: "Beef", value: 2, note: "6 kg on hand", status: "low" }] }],
  extra_tables: [{ title: "Suggested order list", note: "Worked out from your recipes and expected sales.", columns: ["Supplier", "What to order"], rows: [["Meat & fish partner", "Beef 16 kg"]] }],
  forecast: [],
  forecast_method: "",
};

const revenueArea = {
  ...stockArea,
  key: "revenue",
  title: "Revenue",
  headline: "You took KES 61,200 today.",
  attention: [],
  decisions: [],
  charts: [
    {
      type: "line_band",
      title: "Sales: last 14 days and the next 7",
      actual: [{ date: "2026-09-30", day: "Wed", revenue: 61200 }],
      forecast: [
        { date: "2026-10-01", day: "Thu", revenue: 59670, low: 49420, high: 69920 },
        { date: "2026-10-05", day: "Mon", revenue: 50685, low: 40000, high: 60000 },
      ],
    },
  ],
  forecast: [
    { date: "2026-10-01", day: "Thursday", revenue: 59670, low: 49420, high: 69920, why: "Thursdays are close to a typical day." },
    { date: "2026-10-05", day: "Monday", revenue: 50685, low: 40000, high: 60000, why: "Mondays are one of your quieter days." },
  ],
  forecast_method: "We look at how each weekday has done over the last 8 weeks.",
};

beforeEach(() => {
  vi.clearAllMocks();
  RETRY.delays = [1, 1, 1, 1]; // real waits are seconds long; the behaviour is the same
  window.sessionStorage.clear();
  vi.mocked(api.get).mockImplementation(async (url: string) => ({
    data: url.includes("/pdf")
      ? new Blob(["%PDF-1.4"], { type: "application/pdf" })
      : url.includes("/reports/")
        ? sampleReport
        : url.includes("/areas/revenue")
          ? revenueArea
          : url.includes("/areas/")
            ? stockArea
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

it("renders the demo owner home without the value block or a creative button", async () => {
  render(<DemoHomePage />);
  expect(await screen.findByText("Today at Demo Restaurant")).toBeTruthy();
  expect(screen.getAllByText(/Nothing waits on Macsoft/).length).toBeGreaterThan(0);
  expect(screen.getByText("Nothing needs your attention right now")).toBeTruthy();
  expect(screen.queryByText(/See the value/i)).toBeNull();
  expect(screen.queryByText(/Write a creative take/i)).toBeNull();
  expect(screen.queryByText(/A fresh perspective/i)).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Ask about sales" }));
  expect(push).toHaveBeenCalledWith("/demo/os?q=How%20are%20my%20sales%20today%3F");
  const detailLinks = screen.getAllByRole("link", { name: /Open details/ }).map((a) => a.getAttribute("href"));
  expect(detailLinks).toContain("/demo/revenue");
  expect(detailLinks.every((href) => href?.startsWith("/demo/"))).toBe(true);
});

it("home ends with an ideas box: numbers first, then AI ideas, with no choice to make", async () => {
  vi.mocked(api.post).mockImplementation(async (_url: string, body?: unknown) => ({
    data: (body as { creative: boolean }).creative
      ? { checked: 20, from_numbers: [], creative: ["Try a lunch combo of vegetable bowl and fresh juice."] }
      : {
          checked: 20,
          creative: [],
          from_numbers: [{ area: "Stock", href: "/demo/stock", idea: "Use the older vegetables first", why: "8 kg is close to its date.", next_step: "Cook from the oldest batch.", expected: "KES 1,440 potential saving" }],
        },
  }));
  render(<DemoHomePage />);
  await screen.findByText("Today at Demo Restaurant");
  expect(screen.getByText("Fresh ideas to try this week")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: /Get ideas/ }));
  expect(await screen.findByText("Use the older vegetables first")).toBeTruthy();
  expect(screen.getByText(/We looked at 20 parts of your restaurant/)).toBeTruthy();
  expect(await screen.findByText(/Try a lunch combo/)).toBeTruthy();
  expect(screen.getByText(/Written by AI/)).toBeTruthy();
  expect(vi.mocked(api.post).mock.calls.map((c) => (c[1] as { creative: boolean }).creative)).toEqual([false, true]);
  expect(screen.getByRole("link", { name: /See the numbers/ }).getAttribute("href")).toBe("/demo/stock");
});

it("reports explain themselves in plain words and can be downloaded as a PDF", async () => {
  const createUrl = vi.fn(() => "blob:report");
  Object.defineProperty(URL, "createObjectURL", { value: createUrl, configurable: true });
  Object.defineProperty(URL, "revokeObjectURL", { value: vi.fn(), configurable: true });
  const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  render(<DemoReportsPage />);
  expect(await screen.findByText(/1 sample day available/)).toBeTruthy();
  expect(screen.getByText(/the restaurant took KES 61,200 from 70 orders/)).toBeTruthy();
  expect(screen.getByText("The story in plain words")).toBeTruthy();
  expect(screen.getByText("Where the money went")).toBeTruthy();
  expect(screen.getByText(/Sales are up 6.4% compared with last Wednesday/)).toBeTruthy();
  expect(screen.queryByText(/Macsoft is not connected/)).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: /Download PDF/ }));
  await waitFor(() => expect(click).toHaveBeenCalled());
  expect(api.get).toHaveBeenCalledWith("/api/v1/demo/reports/daily/pdf", { responseType: "blob", timeout: 60000 });
  expect(createUrl).toHaveBeenCalled();
  click.mockRestore();
});

it("area pages explain, flag what needs attention, and suggest with reasons", async () => {
  render(<DemoAreaClient areaKey="stock" view={{ title: "Stock", description: "Keep an eye on ingredients." }} />);
  expect(await screen.findByText("You track 13 ingredients, all used by the dishes on your menu.")).toBeTruthy();
  expect(api.get).toHaveBeenCalledWith("/api/v1/demo/areas/stock");
  expect(screen.getByText("In plain words")).toBeTruthy();
  expect(screen.getByText("What needs your attention here")).toBeTruthy();
  expect(screen.getByText("Beef is running low")).toBeTruthy();
  expect(screen.getByText("What we suggest, and why")).toBeTruthy();
  expect(screen.getByText("Order beef today")).toBeTruthy();
  expect(screen.getByText("Everything on the shelf")).toBeTruthy();
  expect(screen.getByText("Suggested order list")).toBeTruthy();
  expect(screen.getByText("Beef 16 kg")).toBeTruthy();
  expect(screen.getByRole("link", { name: /Back to Home/ }).getAttribute("href")).toBe("/demo");
  fireEvent.click(screen.getByRole("button", { name: "Got it" }));
  expect(screen.queryByText("Beef is running low")).toBeNull();
  expect(screen.getByText("You have looked at everything on this page.")).toBeTruthy();
});

it("each coming day can explain itself on the page, starting with the quietest", async () => {
  render(<DemoAreaClient areaKey="revenue" view={{ title: "Revenue", description: "Understand sales." }} />);
  expect(await screen.findByText("You took KES 61,200 today.")).toBeTruthy();
  expect(screen.getByText(/Mondays are one of your quieter days/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: /Thursday/ }));
  expect(screen.getByText(/Thursdays are close to a typical day/)).toBeTruthy();
  expect(screen.queryByText(/Mondays are one of your quieter days/)).toBeNull();
  expect(push).not.toHaveBeenCalled();
});

it("OS has prompted questions, no focus-area picker and no creative toggle", async () => {
  vi.mocked(api.post).mockImplementation(async (_url: string, body?: unknown) => ({
    data: (body as { creative: boolean }).creative
      ? { answer_text: "Try a vegetable bowl special.", module: "stock", title: "Stock", href: "/demo/stock", creative: true, cached: false, reason: null }
      : {
          answer_text: "Beef covers 2 days.\n\nNeeds attention: order beef.",
          module: "stock",
          title: "Stock",
          href: "/demo/stock",
          creative: false,
          cached: false,
          reason: null,
          follow_ups: ["What should I do about stock?"],
        },
  }));
  render(<DemoOS />);
  expect(screen.getByRole("heading", { level: 1 }).textContent).toContain("What would you like to know");
  expect(screen.queryByText(/Focus area/)).toBeNull();
  expect(screen.queryByText(/Creative adviser/)).toBeNull();
  expect(screen.queryByRole("checkbox")).toBeNull();
  expect(screen.queryByRole("combobox")).toBeNull();
  fireEvent.click(screen.getAllByRole("button", { name: "What am I about to run out of?" })[0]);
  expect(await screen.findByText(/Beef covers 2 days/)).toBeTruthy();
  expect(await screen.findByText("Try a vegetable bowl special.")).toBeTruthy();
  expect(screen.getByText(/An idea to try/)).toBeTruthy();
  expect(vi.mocked(api.post).mock.calls[0]).toEqual([
    "/api/v1/demo/chat",
    { question: "What am I about to run out of?", topic: "stock", creative: false },
    { timeout: 30000 },
  ]);
  expect(vi.mocked(api.post).mock.calls[1]).toEqual([
    "/api/v1/demo/chat",
    { question: "What am I about to run out of?", topic: "stock", creative: true },
    { timeout: 90000 },
  ]);
  expect(screen.getByRole("link", { name: /See the numbers: Stock/ }).getAttribute("href")).toBe("/demo/stock");
});

it("home lists urgent items first, keeps lower ones compact, and lets decisions be undone", async () => {
  const card = (id: string, level: string, title: string) => ({ id, domain: "Stock", title, why: "Because.", what_to_do: "Do it.", impact: "", status: "open", level, link: "stock" });
  const feed = {
    ...emptyFeed,
    period_label: "Today",
    period_note: "Revenue and orders follow the period. Kitchen, stock, bookings and staff always show right now.",
    attention: [card("beef-low", "urgent", "Beef runs out on Friday"), card("waste", "opportunity", "Use vegetables before expiry")],
    watching: [card("soon-out", "watch", "3 more ingredients run out soon")],
    pulse: [{ domain: "Stock", headline: "3 ingredients run out soon", detail: "On the order list.", link: "purchasing" }],
    money_today: { sales: 61200, food_cost: 23440, contribution: 37760, labor: 10500, other: 6500, surplus: 20760 },
    week_ahead: [{ date: "2026-10-01", day: "Thursday", revenue: 59670, low: 49420, high: 69920, plates: 100, people: 8, covers: 41 }],
    roi: { potential_daily: 2910, realised: 0, label: "Illustrative daily opportunity", assumption: "Not guaranteed.", opportunities: [{}, {}, {}] },
  };
  vi.mocked(api.get).mockImplementation(async (url: string) => ({ data: url.includes("/reports/") ? sampleReport : feed }));
  render(<DemoHomePage />);
  expect(await screen.findByText("2 items · 1 urgent")).toBeTruthy();
  expect(screen.getByText("Urgent")).toBeTruthy();
  expect(screen.getByText("Also worth watching")).toBeTruthy();
  expect(screen.getByText("3 more ingredients run out soon")).toBeTruthy();
  expect(screen.getByText("The week ahead")).toBeTruthy();
  expect(screen.getByText(/2,910 a day, if all 3 ideas work/)).toBeTruthy();
  expect(screen.getAllByRole("link", { name: /See the numbers/ })[0].getAttribute("href")).toBe("/demo/stock");
  fireEvent.click(screen.getAllByRole("button", { name: "Not now" })[0]);
  expect(screen.getByText("Set aside for now")).toBeTruthy();
  expect(screen.getByText("1 item")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Bring back" }));
  expect(screen.getByText("2 items · 1 urgent")).toBeTruthy();
  fireEvent.click(screen.getAllByRole("button", { name: "Acknowledge" })[0]);
  expect(screen.getByText(/Acknowledged:/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Undo" }));
  expect(screen.queryByText(/Acknowledged:/)).toBeNull();
});

const homeCalls = () => vi.mocked(api.get).mock.calls.filter((c) => String(c[0]).includes("/demo/home")).length;

it("rides out a short backend restart instead of showing an error", async () => {
  const outage = Object.assign(new Error("Network Error"), { isAxiosError: true });
  let calls = 0;
  vi.mocked(api.get).mockImplementation(async (url: string) => {
    if (url.includes("/demo/home")) {
      calls += 1;
      if (calls <= 2) throw outage;
      return { data: emptyFeed };
    }
    return { data: sampleReport };
  });
  render(<DemoHomePage />);
  expect(await screen.findByText("Today at Demo Restaurant")).toBeTruthy();
  expect(calls).toBe(3);
  expect(screen.queryByText(/couldn't load your restaurant/i)).toBeNull();
});

it("shows a plain message and a retry button only when the outage lasts", async () => {
  const down = Object.assign(new Error("Bad Gateway"), { isAxiosError: true, response: { status: 502 } });
  vi.mocked(api.get).mockImplementation(async (url: string) => {
    if (url.includes("/demo/home")) throw down;
    return { data: sampleReport };
  });
  render(<DemoHomePage />);
  expect(await screen.findByText(/We couldn't load your restaurant just now/)).toBeTruthy();
  expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
  expect(screen.queryByText(/kitchen/i)).toBeNull();
  expect(homeCalls()).toBe(5);
});

it("does not keep retrying a real answer such as an expired login", async () => {
  const expired = Object.assign(new Error("Unauthorized"), { isAxiosError: true, response: { status: 401 } });
  vi.mocked(api.get).mockImplementation(async (url: string) => {
    if (url.includes("/demo/home")) throw expired;
    return { data: sampleReport };
  });
  render(<DemoHomePage />);
  expect(await screen.findByText(/We couldn't load your restaurant just now/)).toBeTruthy();
  expect(homeCalls()).toBe(1);
});

it("area pages and reports also recover from a short outage", async () => {
  const outage = Object.assign(new Error("Network Error"), { isAxiosError: true });
  let areaCalls = 0;
  vi.mocked(api.get).mockImplementation(async (url: string) => {
    if (url.includes("/areas/")) {
      areaCalls += 1;
      if (areaCalls === 1) throw outage;
      return { data: stockArea };
    }
    return { data: sampleReport };
  });
  render(<DemoAreaClient areaKey="stock" view={{ title: "Stock", description: "Ingredients." }} />);
  expect(await screen.findByText("You track 13 ingredients, all used by the dishes on your menu.")).toBeTruthy();
  expect(areaCalls).toBe(2);
});

it("keeps showing the last loaded view, marked as such, if the service stays down", async () => {
  const first = render(<DemoHomePage />);
  expect(await screen.findByText("Today at Demo Restaurant")).toBeTruthy();
  first.unmount();
  const down = Object.assign(new Error("Bad Gateway"), { isAxiosError: true, response: { status: 502 } });
  vi.mocked(api.get).mockImplementation(async (url: string) => {
    if (url.includes("/demo/home")) throw down;
    return { data: sampleReport };
  });
  render(<DemoHomePage />);
  expect(await screen.findByText(/seeing the last view that loaded/)).toBeTruthy();
  expect(screen.getByText("Today at Demo Restaurant")).toBeTruthy();
  expect(screen.queryByText(/We couldn't load your restaurant/)).toBeNull();
});
