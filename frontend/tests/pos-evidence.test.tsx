import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import PosEvidence from "@/components/eleven/PosEvidence";

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock("@/lib/api", () => ({ default: { get, post } }));

const source = {
  durable_inbox_enabled: true, source_bound: false, receipts: 0, by_status: {},
  last_receipt_at: null, last_successful_parse_at: null, backlog: 0,
  completeness: "not_checked", sales_live: null,
  why: "Receipt and parsing are separate milestones.", legacy_receipts: "not_counted_in_this_inbox",
};
const receipt = {
  id: "synthetic-receipt", received_at: "2026-11-09T10:00:00", status: "failed",
  parser_version: "synthetic-parser", attempts: 1, last_attempt_at: "2026-11-09T10:00:00",
  parsed_at: null, error_code: "mapping_failed", payload_sha256: "synthetic-hash",
};

beforeEach(() => { vi.resetAllMocks(); });
afterEach(cleanup);

describe("QuickSell evidence states", () => {
  it("does not turn a failed API request into a zero-receipt state", async () => {
    get.mockRejectedValue(new Error("unavailable"));
    render(<PosEvidence />);
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.queryByText(/No envelopes recorded/)).toBeNull();
    get.mockImplementation((path: string) => Promise.resolve({ data: path.endsWith("status") ? source : [] }));
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText(/No envelopes recorded/)).toBeTruthy();
  });

  it("explains that the new empty inbox excludes earlier mirror history", async () => {
    get.mockImplementation((path: string) => Promise.resolve({ data: path.endsWith("status") ? source : [] }));
    render(<PosEvidence />);
    expect(await screen.findByText(/does not count earlier mirror records/)).toBeTruthy();
    expect(screen.getByText("Not checked")).toBeTruthy();
    expect(screen.queryByText("Sales live")).toBeNull();
  });

  it("shows parser failures as retained evidence and formats server time in Nairobi", async () => {
    get.mockImplementation((path: string) => Promise.resolve({ data: path.endsWith("status")
      ? { ...source, receipts: 1, backlog: 1, source_bound: true } : [receipt] }));
    render(<PosEvidence />);
    expect(await screen.findByText("Review reason: mapping failed")).toBeTruthy();
    expect(screen.getByText(/13:00 EAT|1:00 pm EAT/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Retry parser" })).toBeTruthy();
  });

  it("reports an unresolved replay honestly and prevents a duplicate in-flight click", async () => {
    get.mockImplementation((path: string) => Promise.resolve({ data: path.endsWith("status")
      ? { ...source, receipts: 1, backlog: 1 } : [receipt] }));
    let finish: (value: unknown) => void = () => {};
    post.mockImplementation(() => new Promise(resolve => { finish = resolve; }));
    render(<PosEvidence />);
    fireEvent.click(await screen.findByRole("button", { name: "Retry parser" }));
    expect(screen.getByRole("button", { name: "Checking receipt…" }).hasAttribute("disabled")).toBe(true);
    finish({ data: { parse_status: "failed", orders_inserted: 0, orders_updated: 0 } });
    expect(await screen.findByText(/payload still needs parser review/)).toBeTruthy();
    expect(post).toHaveBeenCalledTimes(1);
  });

  it("does not claim success when replay confirmation fails", async () => {
    get.mockImplementation((path: string) => Promise.resolve({ data: path.endsWith("status")
      ? { ...source, receipts: 1, backlog: 1 } : [receipt] }));
    post.mockRejectedValue(new Error("offline"));
    render(<PosEvidence />);
    fireEvent.click(await screen.findByRole("button", { name: "Retry parser" }));
    await waitFor(() => expect(screen.getByText(/Replay was not confirmed/)).toBeTruthy());
  });
});
