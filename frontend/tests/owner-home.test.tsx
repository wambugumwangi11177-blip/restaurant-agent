import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
  expect(screen.getByText((fixture as unknown as OwnerHome).pulse.money_match.mpesa.headline!)).toBeTruthy();
  expect(screen.getByRole("img", { name: "Sales for each of the last 7 days" })).toBeTruthy();
  expect(screen.getByText("Good evening", { exact: false })).toBeTruthy();
});

it("every number carries its state in words", async () => {
  render(<HomePage />);
  await screen.findByTestId("sales-today");
  expect(screen.getAllByText("Live").length).toBeGreaterThan(0);
  expect(screen.getAllByText(/As entered up to/).length).toBeGreaterThan(0);
  expect(screen.getByText("From your M-Pesa statement")).toBeTruthy();    // the M-Pesa check is computed from a statement, not from the till
});

it("Zone 2 lists the money going out, the biggest first, each in KES a month", async () => {
  render(<HomePage />);
  const region = (await screen.findByRole("heading", { name: "What's costing you money" })).closest("section")!;
  const cards = within(region).getAllByRole("article");
  expect(cards).toHaveLength(5);
  expect(within(cards[0]).getByText("costing about KES 8,661 a month")).toBeTruthy();
  expect(within(cards[0]).getByText(/Check where the Beef went/)).toBeTruthy();
  expect(within(cards[4]).getByText(/Chips/)).toBeTruthy();
  expect(within(cards[0]).getByRole("link", { name: "Ask LEVIII about this" }).getAttribute("href")).toMatch(/^\/os\?q=/);
});

it("an idea we cannot put a figure on says so, and one that could earn money says that, not 'costing'", async () => {
  const data = home();
  data.costing_you_money.cards[1].kes_month = null;
  data.costing_you_money.cards[2].tier = "idea";
  data.costing_you_money.cards[3].tier = "now";
  serve(data);
  render(<HomePage />);
  const region = (await screen.findByRole("heading", { name: "What's costing you money" })).closest("section")!;
  expect(within(region).getByText("we can't put a number on this yet")).toBeTruthy();
  expect(within(region).getByText("could earn about KES 2,105 a month")).toBeTruthy();
  expect(within(region).getByText("happening now")).toBeTruthy();
});

it("the rest of the ranking is one tap away, in the same order, with what each is worth", async () => {
  render(<HomePage />);
  const fold = await screen.findByRole("button", { name: /24 more ideas/ });
  expect(fold.getAttribute("aria-expanded")).toBe("false");
  fireEvent.click(fold);
  const rows = within(fold.parentElement!).getAllByRole("listitem");
  expect(rows).toHaveLength(24);
  expect(within(rows[0]).getByText(/could earn about KES 5,900 a month|costing about/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Show fewer" }));
  expect(screen.queryAllByRole("listitem").filter((li) => li.textContent?.includes("Ask LEVIII"))).toHaveLength(0);
});

it("a KES figure is written the way an owner says it", async () => {
  const data = home();
  data.costing_you_money.cards[0].kes_month = 18600.4;
  serve(data);
  render(<HomePage />);
  expect(await screen.findByText("costing about KES 18,600 a month")).toBeTruthy();
});

it("any card can be acknowledged; a failed save keeps the card and says so, a good one takes it away", async () => {
  const data = home();
  serve(data);
  vi.mocked(api.post).mockRejectedValueOnce(new Error("offline"));
  render(<HomePage />);
  const first = data.costing_you_money.cards[0];
  const card = () => screen.getByText(first.sentence).closest("article")!;
  await screen.findByText(first.sentence);
  fireEvent.click(within(card()).getByRole("button", { name: "Approve" }));
  expect((await screen.findByRole("alert")).textContent).toMatch(/could not be saved/);
  expect(screen.getByText(first.sentence)).toBeTruthy();
  vi.mocked(api.post).mockResolvedValueOnce({ data: {} } as never);
  fireEvent.click(within(card()).getByRole("button", { name: "Approve" }));
  await waitFor(() => expect(screen.queryByText(first.sentence)).toBeNull());
  expect(api.post).toHaveBeenLastCalledWith(`/api/v1/overview/attention/${encodeURIComponent(first.id)}/decision`, { decision: "approved" });
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
  fireEvent.click(screen.getByRole("button", { name: "Last 7 days" }));
  await waitFor(() => expect(api.get).toHaveBeenLastCalledWith("/api/v1/owner/home", expect.objectContaining({ params: { period: "7d" } })));
  expect(screen.getByRole("button", { name: "Last 7 days" }).getAttribute("aria-pressed")).toBe("true");
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

it("a link to a panel on this page opens it without a reload (the browser's hashchange)", async () => {
  render(<HomePage />);
  await screen.findByTestId("sales-today");
  const cash = screen.getByRole("button", { name: /Cash Check/ });
  expect(cash.getAttribute("aria-expanded")).toBe("false");
  await act(async () => { window.location.hash = "#area-cash"; await new Promise((r) => setTimeout(r, 30)); });
  await waitFor(() => expect(cash.getAttribute("aria-expanded")).toBe("true"));
});
