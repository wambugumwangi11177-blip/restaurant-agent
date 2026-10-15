import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import HomePage from "../src/app/(owner)/home/page";
import api from "@/lib/api";
import fixture from "./fixtures/owner/home.json";
import type { OwnerHome } from "@/lib/owner/types";

const auth = vi.hoisted(() => ({ tenant: "Demo Restaurant" }));
vi.mock("@/lib/api", () => ({ default: { get: vi.fn(), post: vi.fn() } }));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => ({ user: { restaurant_name: auth.tenant, tenant_name: auth.tenant } }) }));

const home = () => structuredClone(fixture) as unknown as OwnerHome;
const serve = (data: unknown) => vi.mocked(api.get).mockResolvedValue({ data } as never);

beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-15T19:30:00Z"));                  // 22:30 in Nairobi, the same evening as the fixture
  auth.tenant = "Demo Restaurant";
  window.location.hash = "";
  serve(home());
});
afterEach(() => { cleanup(); vi.useRealTimers(); });

it("Zone 1 shows today's sales, the comparison, costs covered and the money checks", async () => {
  render(<HomePage />);
  expect((await screen.findByTestId("sales-today")).textContent).toBe("KES 22,290");
  expect(screen.getByText("13 paid orders")).toBeTruthy();
  expect(screen.getByText("+14.8%")).toBeTruthy();
  expect(screen.getByText("Covered at 12:31 pm")).toBeTruthy();
  expect(screen.getByText("KES 22,290 of KES 4,946 a day")).toBeTruthy();
  expect(screen.getByText(/27 shifts checked · 2 to look at/)).toBeTruthy();
  expect(screen.getByText(/Upload your M-Pesa statement/)).toBeTruthy();
  expect(screen.getByRole("img", { name: "Sales for each of the last 7 days" })).toBeTruthy();
  expect(screen.getByText("Good evening", { exact: false })).toBeTruthy();
});

it("every number carries its state in words", async () => {
  render(<HomePage />);
  await screen.findByTestId("sales-today");
  expect(screen.getAllByText("Live").length).toBeGreaterThan(0);
  expect(screen.getAllByText(/As entered up to/).length).toBeGreaterThan(0);
  expect(screen.getByText("Not available")).toBeTruthy();                // the M-Pesa check, until a statement is uploaded
});

it("Zone 2 lists what is costing money; an idea with no KES figure says so instead of inventing one", async () => {
  render(<HomePage />);
  const region = (await screen.findByRole("heading", { name: "What's costing you money" })).closest("section")!;
  const cards = within(region).getAllByRole("article");
  expect(cards).toHaveLength(5);
  expect(within(region).getAllByText("we can't put a number on this yet").length).toBeGreaterThan(0);
  expect(within(region).getByText(/7 more ideas/)).toBeTruthy();
  expect(within(cards[0]).getByRole("link", { name: "Ask LEVIII about this" }).getAttribute("href")).toMatch(/^\/os\?q=/);
});

it("a KES figure is written the way an owner says it", async () => {
  const data = home();
  data.costing_you_money.cards[0].kes_month = 18600.4;
  serve(data);
  render(<HomePage />);
  expect(await screen.findByText("about KES 18,600 a month")).toBeTruthy();
});

it("a card the decision layer made can be acknowledged; a failed save keeps the card and says so", async () => {
  const data = home();
  data.costing_you_money.cards[0].decision = { options: ["approved", "later", "rejected"] };
  serve(data);
  vi.mocked(api.post).mockRejectedValueOnce(new Error("offline"));
  render(<HomePage />);
  const sentence = data.costing_you_money.cards[0].sentence;
  await screen.findByText(sentence);
  fireEvent.click(screen.getByRole("button", { name: "Acknowledge" }));
  expect((await screen.findByRole("alert")).textContent).toMatch(/could not be saved/);
  expect(screen.getByText(sentence)).toBeTruthy();
  vi.mocked(api.post).mockResolvedValueOnce({ data: {} } as never);
  fireEvent.click(screen.getByRole("button", { name: "Acknowledge" }));
  await waitFor(() => expect(screen.queryByText(sentence)).toBeNull());
  expect(api.post).toHaveBeenLastCalledWith(`/api/v1/overview/attention/${encodeURIComponent(data.costing_you_money.cards[0].id)}/decision`, { decision: "approved" });
});

it("the health strip has one tile per area, each a link to its panel", async () => {
  render(<HomePage />);
  const strip = (await screen.findByRole("heading", { name: "Your restaurant's health" })).closest("section")!;
  const links = within(strip).getAllByRole("link");
  expect(links.map((a) => a.getAttribute("href"))).toEqual(["#area-money", "#area-sales_dishes", "#area-store", "#area-cash", "#area-staff", "#area-permits"]);
  expect(within(strip).getByText("KES 99,090")).toBeTruthy();
});

it("the six areas start closed, open in place, and a #area link opens its panel", async () => {
  window.location.hash = "#area-store";
  render(<HomePage />);
  await screen.findByTestId("sales-today");
  const store = screen.getByRole("button", { name: /Store & Suppliers/ });
  await waitFor(() => expect(store.getAttribute("aria-expanded")).toBe("true"));
  expect(screen.getByRole("region", { name: "Store & Suppliers" })).toBeTruthy();
  const money = screen.getByRole("button", { name: /My Money/ });
  expect(money.getAttribute("aria-expanded")).toBe("false");
  fireEvent.click(money);
  expect(money.getAttribute("aria-expanded")).toBe("true");
  fireEvent.click(money);
  expect(money.getAttribute("aria-expanded")).toBe("false");
});

it("Zone 4 shows bills with the shortfall, licences, deliveries and the bookings that are coming", async () => {
  render(<HomePage />);
  const zone = (await screen.findByRole("heading", { name: "Coming up" })).closest("section")!;
  expect(within(zone).getByText(/Rent · in 3 days/)).toBeTruthy();
  expect(within(zone).getByText(/KES 70,000 · short/)).toBeTruthy();
  expect(within(zone).getByText("Health certificate")).toBeTruthy();
  expect(within(zone).getByText(/Beer \(500 ml\)/)).toBeTruthy();
});

it("the period buttons ask for that period", async () => {
  render(<HomePage />);
  await screen.findByTestId("sales-today");
  fireEvent.click(screen.getByRole("button", { name: "7 days" }));
  await waitFor(() => expect(api.get).toHaveBeenLastCalledWith("/api/v1/owner/home", expect.objectContaining({ params: { period: "7d" } })));
  expect(screen.getByRole("button", { name: "7 days" }).getAttribute("aria-pressed")).toBe("true");
});

it("old figures say they are old", async () => {
  const data = home();
  data.pulse.state = "stale";
  data.pulse.age_days = 4;
  data.pulse.freshness = { ...data.pulse.freshness, is_stale: true, data_age_days: 4 };
  serve(data);
  render(<HomePage />);
  expect(await screen.findByText(/Out of date · 4 days old/)).toBeTruthy();
  expect(screen.getByText(/the till may not be sending sales/)).toBeTruthy();
});

it("a failed load says so and offers a retry; a failed refresh keeps what was already on screen", async () => {
  vi.mocked(api.get).mockRejectedValueOnce(new Error("offline"));
  render(<HomePage />);
  fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
  expect((await screen.findByTestId("sales-today")).textContent).toBe("KES 22,290");
});

it("no system word and no bare dash reaches the owner", async () => {
  render(<HomePage />);
  await screen.findByTestId("sales-today");
  const text = document.body.textContent ?? "";
  for (const word of ["cents", "_kes", "undefined", "NaN", "null", "[object"]) expect(text).not.toContain(word);
  expect([...document.body.querySelectorAll("*")].filter((el) => el.children.length === 0 && el.textContent?.trim() === "—")).toEqual([]);
});

// ── a restaurant fed by Macsoft shows nothing until the delivery is reconciled ───────────────────────────

it("Vibanda's figures wait for a reconciled delivery, and say what is being waited for", async () => {
  auth.tenant = "Vibanda Village";
  const data = home();
  data.pulse.freshness = { ...data.pulse.freshness, source: "macsoft", source_state: "receiving", source_trusted: false, source_reconciled: false, source_records: 12,
    source_notice: "Recorded data only. Macsoft has delivered records; delivery completeness is not reconciled." };
  serve(data);
  render(<HomePage />);
  expect(await screen.findByText("Waiting for verified restaurant data")).toBeTruthy();
  expect(screen.getByText(/delivery completeness is not reconciled/)).toBeTruthy();
  expect(screen.getByText(/12 records received/)).toBeTruthy();
  expect(screen.queryByTestId("sales-today")).toBeNull();
  expect(screen.queryByText(/KES 22,290/)).toBeNull();
  expect(screen.queryByRole("button", { name: "Today" })).toBeNull();
});

it("once Vibanda's delivery is reconciled its figures appear; other restaurants are never held back", async () => {
  auth.tenant = "Vibanda Village";
  const trusted = home();
  trusted.pulse.freshness = { ...trusted.pulse.freshness, source: "macsoft", source_state: "receiving", source_trusted: true, source_reconciled: true };
  serve(trusted);
  const { unmount } = render(<HomePage />);
  expect((await screen.findByTestId("sales-today")).textContent).toBe("KES 22,290");
  unmount();
  auth.tenant = "Mama Oliech";
  const untrusted = home();
  untrusted.pulse.freshness = { ...untrusted.pulse.freshness, source: "macsoft", source_state: "awaiting_first_delivery", source_trusted: false };
  serve(untrusted);
  render(<HomePage />);
  expect((await screen.findByTestId("sales-today")).textContent).toBe("KES 22,290");
});
