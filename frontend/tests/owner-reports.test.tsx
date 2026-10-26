import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import ReportsPage from "../src/app/(owner)/reports/page";
import api from "@/lib/api";
import { lastMonths } from "@/lib/owner/format";
import daily from "./fixtures/owner/report_daily.json";
import weekly from "./fixtures/owner/report_weekly.json";
import monthly from "./fixtures/owner/report_monthly.json";
import yearly from "./fixtures/owner/report_yearly.json";

vi.mock("@/lib/api", () => ({ default: { get: vi.fn(), post: vi.fn() } }));
const auth = vi.hoisted(() => ({ tenant: "Demo Restaurant" }));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => ({ user: { restaurant_name: "Demo", tenant_name: auth.tenant } }) }));

const REPORTS: Record<string, unknown> = { daily, weekly, monthly, yearly };
const seen = () => vi.mocked(api.get).mock.calls.map(([url, config]) => ({ url: url as string, params: (config as { params?: unknown } | undefined)?.params }));

function respond(over: { connection?: unknown; creative?: unknown } = {}) {
  vi.mocked(api.get).mockImplementation((url: string) => {
    const m = /\/owner\/report\/(\w+)$/.exec(url);
    if (m) return Promise.resolve({ data: REPORTS[m[1]] }) as never;
    if (url.includes("/creative")) return Promise.resolve({ data: over.creative ?? { surface: "reports", mode: "report_take", period: "daily", text: "My read: lunch carries the day.", stale: false, generated_at: "2026-09-29T12:05:00" } }) as never;
    if (url.includes("/overview/today")) return Promise.resolve({ data: { data_provenance: { source_connection: over.connection } } }) as never;
    return Promise.reject(new Error(`unexpected ${url}`)) as never;
  });
}

beforeEach(() => { window.history.replaceState({},"","/reports");vi.clearAllMocks(); auth.tenant = "Demo Restaurant"; respond(); });
afterEach(cleanup);

describe("the four reports", () => {
  it("opens on the daily report, built from the owner API, with every section it plans", async () => {
    render(<ReportsPage />);
    await screen.findByRole("region", { name: "Cash count check" });
    expect(seen().some((c) => c.url === "/api/v1/owner/report/daily")).toBe(true);
    expect(seen().some((c) => c.url.startsWith("/api/v1/reports/") && !c.url.endsWith("/creative"))).toBe(false);      // not the old report
    for (const title of daily.sections.map((s) => s.title)) expect(screen.getByRole("region", { name: title })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Daily" }).getAttribute("aria-selected")).toBe("true");
  });

  it("each tab asks for its own report and draws all of its sections", async () => {
    render(<ReportsPage />);
    await screen.findByRole("region", { name: "Cash count check" });
    for (const [tab, report] of [["Weekly", weekly], ["Monthly", monthly], ["Yearly", yearly]] as const) {
      fireEvent.click(screen.getByRole("tab", { name: tab }));
      await screen.findAllByText(new RegExp(report.range.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
      expect(seen().some((c) => c.url === `/api/v1/owner/report/${tab.toLowerCase()}`)).toBe(true);
      for (const s of report.sections) expect(screen.getAllByRole("region", { name: s.title }).length, `${tab}: ${s.title}`).toBeGreaterThan(0);
    }
  });

  it("no section says it is planned, and no figure is a dash", async () => {
    render(<ReportsPage />);
    for (const tab of ["Daily", "Weekly", "Monthly", "Yearly"]) {
      fireEvent.click(screen.getByRole("tab", { name: tab }));
      await screen.findByRole("tab", { name: tab, selected: true });
      await waitFor(() => expect(screen.queryByText(/Working on|Loading/)).toBeNull());
      const text = document.body.textContent ?? "";
      expect(text).not.toMatch(/planned|not available yet|Planned feature/i);
      expect(text).not.toMatch(/\s—\s*(?:KES|$)/);
    }
  });

  it("a section is its sentence, its figures and what it rests on, with its state and the days it covers", async () => {
    render(<ReportsPage />);
    fireEvent.click(screen.getByRole("tab", { name: "Weekly" }));
    const suppliers = await screen.findByRole("region", { name: "Suppliers" });
    const section = weekly.sections.find((s) => s.key === "suppliers")!;
    expect(within(suppliers).getByText(section.headline!)).toBeTruthy();
    expect(within(suppliers).getByText(section.window)).toBeTruthy();
    expect(within(suppliers).getByText("What this rests on")).toBeTruthy();
    for (const r of section.rows.filter((r) => r.key === "supplier")) expect(within(suppliers).getByText(r.label)).toBeTruthy();
  });

  it("a section with nothing to say shows its reason, not an empty box", async () => {
    render(<ReportsPage />);
    const cash = await screen.findByRole("region", { name: "Cash count check" });
    const section = daily.sections.find((s) => s.key === "cash_check")!;
    expect(section.state).toBe("no_data");
    expect(within(cash).getByRole("status").textContent).toBe(section.reason);
  });

  it("the monthly report has the Profit & Loss Home has, and the accountant's file under it", async () => {
    render(<ReportsPage />);
    fireEvent.click(screen.getByRole("tab", { name: "Monthly" }));
    const pnl = await screen.findByRole("region", { name: "Profit & Loss" });
    expect(within(pnl).getAllByText(/October 2026/).length).toBeGreaterThan(0);
    expect(within(pnl).getByText("For your accountant")).toBeTruthy();
    expect(within(pnl).getByRole("button", { name: /Excel/ })).toBeTruthy();
  });

  it("the yearly report draws its months as a chart, and lists them month by month", async () => {
    render(<ReportsPage />);
    fireEvent.click(screen.getByRole("tab", { name: "Yearly" }));
    const trends = await screen.findByRole("region", { name: "Trends" });
    expect(within(trends).getByRole("img", { name: "Sales by month, last 12 months" })).toBeTruthy();
    expect(within(trends).getAllByRole("img", { hidden: true }).length).toBeGreaterThan(0);
    fireEvent.click(within(trends).getByText("Month by month"));
    const series = yearly.sections.find((s) => s.key === "trends")!.series!;
    expect(within(trends).getByText(`${series[series.length - 1].label} so far`)).toBeTruthy();
  });
});

describe("choosing a month", () => {
  it("offers the last twelve months, this one marked 'so far', and asks for the one chosen", async () => {
    render(<ReportsPage />);
    fireEvent.click(screen.getByRole("tab", { name: "Monthly" }));
    const select = await screen.findByLabelText("Month") as HTMLSelectElement;
    expect(select.options).toHaveLength(12);
    expect(select.options[0].textContent).toMatch(/\(so far\)$/);
    expect(select.options[0].value).toBe(lastMonths()[0].value);
    fireEvent.change(select, { target: { value: select.options[1].value } });
    await waitFor(() => expect(seen().some((c) => c.url === "/api/v1/owner/report/monthly" && JSON.stringify(c.params) === JSON.stringify({ month: select.options[1].value }))).toBe(true));
    // the first request for the month so far carried no month at all
    expect(seen().find((c) => c.url === "/api/v1/owner/report/monthly")!.params).toBeUndefined();
  });

  it("the month picker is only for the monthly report", async () => {
    render(<ReportsPage />);
    expect(screen.queryByLabelText("Month")).toBeNull();
    fireEvent.click(screen.getByRole("tab", { name: "Weekly" }));
    await screen.findByRole("region", { name: "Price ideas" });
    expect(screen.queryByLabelText("Month")).toBeNull();
  });

  it("lists months by Nairobi's calendar, newest first", () => {
    const months = lastMonths(new Date("2026-10-31T22:00:00Z"));                               // 01 Nov in Nairobi
    expect(months[0]).toEqual({ value: "2026-11", label: "November 2026" });
    expect(months[1].value).toBe("2026-10");
    expect(months).toHaveLength(12);
    expect(lastMonths(new Date("2026-01-15T10:00:00Z"))[2]).toEqual({ value: "2025-11", label: "November 2025" });
  });
});

describe("the writing assistant's take", () => {
  it("is shown for a period with sales, loaded separately from the report", async () => {
    render(<ReportsPage />);
    await screen.findByRole("region", { name: "Cash count check" });
    expect(await screen.findByText("My read: lunch carries the day.")).toBeTruthy();
    expect(screen.getByText("Creative take · AI-written")).toBeTruthy();
    expect(seen().map((c) => c.url)).toContain("/api/v1/reports/daily/creative");
  });

  it("is not asked for when nothing was sold, nor for a month that is over", async () => {
    const empty = { ...daily, state: "no_data", sections: daily.sections.map((s) => s.key === "sales" ? { ...s, state: "no_data", orders: 0, reason: "No sales recorded in this period." } : s) };
    REPORTS.daily = empty;
    render(<ReportsPage />);
    await screen.findByRole("region", { name: "Sales" });
    expect(screen.getByText(/Nothing is recorded for this report yet/)).toBeTruthy();
    expect(seen().some((c) => c.url.includes("/creative"))).toBe(false);
    REPORTS.daily = daily;
    cleanup();
    vi.clearAllMocks();
    respond();
    render(<ReportsPage />);
    fireEvent.click(screen.getByRole("tab", { name: "Monthly" }));
    const select = await screen.findByLabelText("Month") as HTMLSelectElement;
    await screen.findByRole("region", { name: "Profit & Loss" });
    vi.mocked(api.get).mockClear();
    fireEvent.change(select, { target: { value: select.options[2].value } });
    await waitFor(() => expect(seen().some((c) => c.url === "/api/v1/owner/report/monthly")).toBe(true));
    await screen.findByRole("region", { name: "Profit & Loss" });
    expect(seen().some((c) => c.url.includes("/creative"))).toBe(false);
  });

  it("a report that cannot be built says so and offers to try again", async () => {
    vi.mocked(api.get).mockImplementation(() => Promise.reject(new Error("down")) as never);
    render(<ReportsPage />);
    expect(await screen.findByText("Couldn't build the report right now.")).toBeTruthy();
    expect(screen.getByRole("button", { name: /try again|retry/i })).toBeTruthy();
  });
});

describe("a restaurant whose figures are a mirror of its till states the real source position", () => {
  const macsoft = (connection: unknown) => { auth.tenant = "Vibanda Village"; respond({ connection }); };

  it("never calls the restaurant's own data a prototype", async () => {
    macsoft({ source: "macsoft", state: "awaiting_first_delivery", records: 0, last_received_at: null, reconciled: false });
    render(<ReportsPage />);
    await screen.findByText(/Macsoft has not delivered any records yet/);
    expect(screen.queryByText(/prototype/i)).toBeNull();
  });

  it("reports delivery once records arrive, without claiming they are complete", async () => {
    macsoft({ source: "macsoft", state: "receiving", records: 1204, last_received_at: "2026-09-19T11:30:00", reconciled: false });
    render(<ReportsPage />);
    const line = await screen.findByText(/Macsoft connected/);
    expect(line.textContent).toContain("1,204 records received");
    expect(line.textContent).toContain("completeness not reconciled");
  });

  it("distinguishes an unreadable source from an unconnected one", async () => {
    macsoft({ source: "macsoft", state: "unavailable", records: null, last_received_at: null, reconciled: false });
    render(<ReportsPage />);
    await screen.findByText(/delivery state unavailable/);
    expect(screen.queryByText(/not delivered any records/)).toBeNull();
  });

  it("says nothing about the source when that call fails, rather than guessing", async () => {
    auth.tenant = "Vibanda Village";
    vi.mocked(api.get).mockImplementation((url: string) => (url.includes("/overview/today") ? Promise.reject(new Error("unavailable")) : Promise.resolve({ data: daily })) as never);
    render(<ReportsPage />);
    await screen.findByRole("region", { name: "Sales" });
    await waitFor(() => expect(screen.queryByText(/Macsoft/)).toBeNull());
  });

  it("a restaurant that records its own sales never asks about a source", async () => {
    render(<ReportsPage />);
    await screen.findByRole("region", { name: "Sales" });
    expect(seen().some((c) => c.url.includes("/overview/today"))).toBe(false);
    expect(screen.queryByText(/Macsoft/)).toBeNull();
  });
});
