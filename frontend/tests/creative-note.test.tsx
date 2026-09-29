import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import CreativeNote from "../src/components/vibanda/CreativeNote";
import api from "@/lib/api";

vi.mock("@/lib/api", () => ({ default: { get: vi.fn(), post: vi.fn() } }));

const ENDPOINT = "/api/v1/ai/creative/home?period=today";
const calls = () => vi.mocked(api.get).mock.calls.map(([url]) => url as string);
const settle = () => act(async () => { await Promise.resolve(); });

function respondWith(handler: (url: string) => unknown) {
  vi.mocked(api.get).mockImplementation(((url: string) => {
    const result = handler(url);
    return result instanceof Promise ? result : Promise.resolve({ data: result });
  }) as never);
}

const story = {
  surface: "home", mode: "today_story", period: "today", text: "A steady lunch. An idea to test: a lunch special.",
  llm_used: true, generated_at: "2026-09-29T12:05:00", stale: false, reason: null, dropped_sentences: 0,
};

beforeEach(() => vi.clearAllMocks());
afterEach(cleanup);

describe("CreativeNote", () => {
  it("shows the text with an AI-written label, a disclaimer and the Nairobi time it was written", async () => {
    respondWith(() => story);
    render(<CreativeNote endpoint={ENDPOINT} />);
    expect(await screen.findByText(story.text)).toBeTruthy();
    expect(screen.getByText("Today’s story · AI-written")).toBeTruthy();
    expect(screen.getByText(/ideas are suggestions to test/i)).toBeTruthy();
    // 12:05 UTC is 15:05 in Nairobi; the naive backend timestamp must be read as UTC.
    expect(screen.getByText("Written 15:05")).toBeTruthy();
    expect(screen.getByRole("region", { name: "Today’s story · AI-written" }).getAttribute("aria-live")).toBe("polite");
    expect(calls()).toEqual([ENDPOINT]);
  });

  it.each([
    ["system_story", "About your Restaurant OS · AI-written", /describes the software, not your results/i],
    ["report_take", "Creative take · AI-written", /an idea to test, not a verified finding/i],
  ])("labels a %s honestly", async (mode, eyebrow, disclaimer) => {
    respondWith(() => ({ ...story, mode }));
    render(<CreativeNote endpoint={ENDPOINT} />);
    expect(await screen.findByText(eyebrow)).toBeTruthy();
    expect(screen.getByText(disclaimer)).toBeTruthy();
  });

  it.each([
    ["a payload with no text", { surface: "home" }],
    ["null text", { ...story, text: null, reason: "disabled" }],
    ["blank text", { ...story, text: "   " }],
    ["a non-string text", { ...story, text: 42 }],
    ["an overview-style feed (the mock every Home test uses)", { restaurant_name: "Vibanda", revenue: { revenue: 500 } }],
  ])("renders nothing for %s", async (_name, payload) => {
    respondWith(() => payload);
    const { container } = render(<CreativeNote endpoint={ENDPOINT} />);
    await settle();
    await settle();
    expect(container.innerHTML).toBe("");
    expect(calls()).toEqual([ENDPOINT]);
  });

  it("renders nothing when the request fails", async () => {
    respondWith(() => Promise.reject(new Error("offline")));
    const { container } = render(<CreativeNote endpoint={ENDPOINT} />);
    await settle();
    await settle();
    expect(container.innerHTML).toBe("");
  });

  it("shows stale text at once, then refreshes exactly once in the background and swaps it", async () => {
    respondWith((url) => url.includes("refresh=1")
      ? { ...story, text: "A brand new take.", stale: false }
      : { ...story, text: "An older take.", stale: true });
    const { rerender } = render(<CreativeNote endpoint={ENDPOINT} />);
    expect(await screen.findByText("A brand new take.")).toBeTruthy();
    expect(screen.queryByText("An older take.")).toBeNull();
    expect(calls()).toEqual([ENDPOINT, `${ENDPOINT}&refresh=1`]);
    rerender(<CreativeNote endpoint={ENDPOINT} />);
    await settle();
    expect(calls()).toHaveLength(2);
  });

  it("keeps the stale text when the background refresh fails", async () => {
    respondWith((url) => url.includes("refresh=1") ? Promise.reject(new Error("offline")) : { ...story, stale: true });
    render(<CreativeNote endpoint={ENDPOINT} />);
    expect(await screen.findByText(story.text)).toBeTruthy();
    await settle();
    expect(screen.getByText(story.text)).toBeTruthy();
    expect(calls()).toHaveLength(2);
  });

  it("does not retry after a refresh that already failed, and says why", async () => {
    respondWith(() => ({ ...story, stale: true, refresh_failed: true, reason: "budget_reached" }));
    render(<CreativeNote endpoint={ENDPOINT} />);
    expect(await screen.findByText(story.text)).toBeTruthy();
    expect(screen.getByText(/budget is used up/i)).toBeTruthy();
    await settle();
    expect(calls()).toEqual([ENDPOINT]);
  });

  it("explains a provider failure but stays silent about reasons the owner cannot act on", async () => {
    respondWith(() => ({ ...story, stale: true, refresh_failed: true, reason: "provider_error" }));
    const first = render(<CreativeNote endpoint={ENDPOINT} />);
    expect(await screen.findByText(/couldn’t be written just now/i)).toBeTruthy();
    first.unmount();
    respondWith(() => ({ ...story, stale: true, refresh_failed: true, reason: "ungrounded" }));
    render(<CreativeNote endpoint={ENDPOINT} />);
    expect(await screen.findByText(story.text)).toBeTruthy();
    expect(screen.queryByText(/couldn’t be written/i)).toBeNull();
    expect(screen.queryByText(/budget/i)).toBeNull();
  });

  it("writes another take on request and disables the button while it does", async () => {
    let finish!: (value: { data: unknown }) => void;
    const pending = new Promise<{ data: unknown }>((resolve) => { finish = resolve; });
    respondWith((url) => url.includes("refresh=1") ? pending : story);
    render(<CreativeNote endpoint={ENDPOINT} />);
    fireEvent.click(await screen.findByRole("button", { name: "Try another take" }));
    const busy = await screen.findByRole("button", { name: /writing another take/i });
    expect((busy as HTMLButtonElement).disabled).toBe(true);
    await act(async () => { finish({ data: { ...story, text: "Another angle entirely." } }); });
    expect(await screen.findByText("Another angle entirely.")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Try another take" }) as HTMLButtonElement).disabled).toBe(false);
    expect(calls()).toEqual([ENDPOINT, `${ENDPOINT}&refresh=1`]);
  });

  it("uses ? or & correctly when the endpoint has no query string", async () => {
    respondWith(() => ({ ...story, mode: "report_take" }));
    render(<CreativeNote endpoint="/api/v1/reports/daily/creative" />);
    fireEvent.click(await screen.findByRole("button", { name: "Try another take" }));
    await waitFor(() => expect(calls()).toContain("/api/v1/reports/daily/creative?refresh=1"));
  });

  it("keeps the current text and says so when another take cannot be written", async () => {
    respondWith((url) => url.includes("refresh=1") ? Promise.reject(new Error("offline")) : story);
    render(<CreativeNote endpoint={ENDPOINT} />);
    fireEvent.click(await screen.findByRole("button", { name: "Try another take" }));
    expect(await screen.findByText(/new take couldn’t be written/i)).toBeTruthy();
    expect(screen.getByText(story.text)).toBeTruthy();
  });

  it("never shows one period's text under another and refetches only when the endpoint changes", async () => {
    let finishWeek!: (value: { data: unknown }) => void;
    const week = new Promise<{ data: unknown }>((resolve) => { finishWeek = resolve; });
    respondWith((url) => url.includes("period=7d") ? week : { ...story, text: "Today’s own words." });
    const { rerender } = render(<CreativeNote endpoint={ENDPOINT} />);
    expect(await screen.findByText("Today’s own words.")).toBeTruthy();
    rerender(<CreativeNote endpoint="/api/v1/ai/creative/home?period=7d" />);
    expect(screen.queryByText("Today’s own words.")).toBeNull();
    await act(async () => { finishWeek({ data: { ...story, period: "7d", text: "The week in a nutshell." } }); });
    expect(await screen.findByText("The week in a nutshell.")).toBeTruthy();
    rerender(<CreativeNote endpoint="/api/v1/ai/creative/home?period=7d" />);
    await settle();
    expect(calls()).toEqual([ENDPOINT, "/api/v1/ai/creative/home?period=7d"]);
  });

  it("ignores a late response for an endpoint the owner has already left", async () => {
    let finishToday!: (value: { data: unknown }) => void;
    const today = new Promise<{ data: unknown }>((resolve) => { finishToday = resolve; });
    respondWith((url) => url.includes("period=today") ? today : { ...story, text: "The week." });
    const { rerender } = render(<CreativeNote endpoint={ENDPOINT} />);
    rerender(<CreativeNote endpoint="/api/v1/ai/creative/home?period=7d" />);
    expect(await screen.findByText("The week.")).toBeTruthy();
    await act(async () => { finishToday({ data: { ...story, text: "Late and wrong." } }); });
    expect(screen.queryByText("Late and wrong.")).toBeNull();
    expect(screen.getByText("The week.")).toBeTruthy();
  });
});
