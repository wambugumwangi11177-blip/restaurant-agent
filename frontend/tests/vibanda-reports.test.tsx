import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import ReportsPage from "../src/app/vibanda/reports/page";
import api from "@/lib/api";

vi.mock("@/lib/api", () => ({ default: { get: vi.fn(), post: vi.fn() } }));

const report = {
  period: "daily", range: "20 Sep", revenue: 500, orders: 2,
  top_items: [], report_text: "Recorded revenue is KSh 500.",
};

function respond(connection: unknown) {
  vi.mocked(api.get).mockImplementation((url: string) =>
    Promise.resolve(url.includes("/overview/today")
      ? { data: { data_provenance: { source_connection: connection } } }
      : { data: report }) as never);
}

beforeEach(() => vi.clearAllMocks());
afterEach(cleanup);

describe("the Reports page states the real source position", () => {
  it("never calls the restaurant's own data a prototype", async () => {
    respond({ source: "macsoft", state: "awaiting_first_delivery", records: 0,
      last_received_at: null, reconciled: false });
    render(<ReportsPage />);
    await screen.findByText(/Macsoft has not delivered any records yet/);
    expect(screen.queryByText(/prototype/i)).toBeNull();
  });

  it("reports delivery once records arrive, without claiming they are complete", async () => {
    respond({ source: "macsoft", state: "receiving", records: 1204,
      last_received_at: "2026-09-19T11:30:00", reconciled: false });
    render(<ReportsPage />);
    const line = await screen.findByText(/Macsoft connected/);
    expect(line.textContent).toContain("1,204 records received");
    expect(line.textContent).toContain("completeness not reconciled");
  });

  it("distinguishes an unreadable source from an unconnected one", async () => {
    respond({ source: "macsoft", state: "unavailable", records: null,
      last_received_at: null, reconciled: false });
    render(<ReportsPage />);
    await screen.findByText(/delivery state unavailable/);
    expect(screen.queryByText(/not delivered any records/)).toBeNull();
  });

  it("says nothing about the source when that call fails, rather than guessing", async () => {
    vi.mocked(api.get).mockImplementation((url: string) =>
      (url.includes("/overview/today")
        ? Promise.reject(new Error("unavailable"))
        : Promise.resolve({ data: report })) as never);
    render(<ReportsPage />);
    await screen.findByText(report.report_text);
    await waitFor(() => expect(screen.queryByText(/Macsoft/)).toBeNull());
  });
});
