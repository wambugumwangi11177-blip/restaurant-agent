import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import AreaBody from "@/components/owner/AreaBody";
import api from "@/lib/api";
import { BLOCK_TITLES } from "@/lib/owner/blocks";
import { AREA_KEYS, type Area, type AreaKey, type OwnerHome } from "@/lib/owner/types";
import fixture from "./fixtures/owner/home.json";

vi.mock("@/lib/api", () => ({ default: { get: vi.fn(), post: vi.fn() } }));
vi.mock("next/link", () => ({ default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => <a href={href} {...rest}>{children}</a> }));

const areas = () => structuredClone((fixture as unknown as OwnerHome).areas);
const open = (key: AreaKey, area: Area = areas()[key]) => render(<AreaBody area={area} />);
const panel = (name: string) => screen.getByRole("region", { name });

beforeEach(() => { vi.clearAllMocks(); vi.useFakeTimers({ toFake: ["Date"] }); vi.setSystemTime(new Date("2026-10-15T19:30:00Z")); });
afterEach(() => { cleanup(); vi.useRealTimers(); });

it.each(AREA_KEYS)("%s: every block the API sends has a titled panel — a new block cannot silently vanish", (key) => {
  open(key);
  for (const block of Object.keys(areas()[key].blocks)) expect(panel(BLOCK_TITLES[key][block]), `${key}.${block}`).toBeTruthy();
});

it.each(AREA_KEYS)("%s: no system word, no cents, no placeholder dash reaches the owner", (key) => {
  open(key);
  const text = document.body.textContent ?? "";
  for (const word of ["cents", "_kes", "undefined", "NaN", "null", "[object", "Infinity"]) expect(text).not.toContain(word);
  expect([...document.querySelectorAll("*")].filter((el) => el.children.length === 0 && el.textContent?.trim() === "—")).toEqual([]);
});

// ── My Money ─────────────────────────────────────────────────────────────────

it("My Money: the P&L runs from sales to what you kept, with the shares out of every KES 100", () => {
  open("money");
  const pnl = panel("Profit & Loss");
  const rows = within(within(pnl).getByRole("list", { name: "Sales down to what you kept" })).getAllByRole("listitem").map((r) => r.textContent);
  expect(rows).toHaveLength(6);
  expect(rows[0]).toMatch(/^Sales.*KES 215,090$/);
  expect(rows[1]).toMatch(/^Ingredients.*− KES 63,317$/);
  expect(rows[5]).toMatch(/^What you kept/);
  expect(within(pnl).getByText("Out of every KES 100 you take")).toBeTruthy();
  expect(within(pnl).getByText(/^October 2026 so far$/)).toBeTruthy();
  expect(within(pnl).getByText(/Delivery app commissions \(estimated\)/)).toBeTruthy();
  const notes = within(pnl).getAllByText(/^No .* entered for this period — you entered it before\.$/);
  expect(new Set(notes.map((n) => n.textContent)).size).toBe(notes.length);               // each sentence once
});

it("My Money: a cost nobody has entered is said, not shown as a flattering profit", () => {
  const a = areas().money;
  a.blocks.pnl = { ...a.blocks.pnl, state: "no_data", reason: "Enter your rent, electricity and other costs to see what you kept." };
  open("money", a);
  expect(within(panel("Profit & Loss")).getByRole("status").textContent).toMatch(/Enter your rent/);
});

it("My Money: the accountant's file downloads as Excel or PDF for the month on screen, and says so if it cannot be made", async () => {
  const createObjectURL = vi.fn(() => "blob:x");
  Object.assign(URL, { createObjectURL, revokeObjectURL: vi.fn() });
  vi.mocked(api.get).mockResolvedValueOnce({ data: new Blob(["x"]) } as never);
  open("money");
  fireEvent.click(screen.getByRole("button", { name: "Excel" }));
  await waitFor(() => expect(api.get).toHaveBeenCalledWith("/api/v1/owner/money/pnl/export", expect.objectContaining({ params: { month: "2026-10", format: "xlsx" }, responseType: "blob" })));
  await waitFor(() => expect(createObjectURL).toHaveBeenCalled());
  vi.mocked(api.get).mockRejectedValueOnce(new Error("nope"));
  fireEvent.click(screen.getByRole("button", { name: "PDF" }));
  expect((await screen.findByRole("alert")).textContent).toMatch(/could not be made/);
});

it("My Money: two dials against the owner's own targets, costs covered, the cash runway and the shortfall in words", () => {
  open("money");
  const dials = within(panel("Ingredients and wages")).getAllByRole("img");
  expect(dials.map((d) => d.getAttribute("aria-label"))).toEqual([
    "Out of every KES 100, ingredients: 29.3%, Fine. Your target is 35%.", "Out of every KES 100, wages: 28.2%, Fine. Your target is 32%."]);
  expect(within(panel("Costs covered")).getByText("Covered at 12:31 pm")).toBeTruthy();
  const bills = panel("Bills coming up");
  expect(within(bills).getByText(/You will be KES 19,406 short on 18 Oct, when Rent falls due\./)).toBeTruthy();
  expect(within(bills).getByRole("img").getAttribute("aria-label")).toMatch(/short on \d+ of the next 30 days/);
  expect(within(panel("Costs going up")).getByText(/Cooking gas/)).toBeTruthy();
  expect(within(panel("Costs going up")).getByText("up 29.8%")).toBeTruthy();
  expect(within(panel("What LEVIII saved you")).getByText("KES 2,508")).toBeTruthy();
});

it("My Money: when the sales cover every bill it says so instead of drawing a shortfall", () => {
  const a = areas().money;
  const bills = a.blocks.bills as unknown as { shortfalls: unknown[]; days: { balance_kes: number }[] };
  bills.shortfalls = [];
  bills.days = bills.days.map((d) => ({ ...d, balance_kes: Math.abs(d.balance_kes) }));
  open("money", a);
  expect(within(panel("Bills coming up")).getByText(/Your sales cover every bill in the next 30 days/)).toBeTruthy();
});

// ── Sales & Dishes ───────────────────────────────────────────────────────────

it("Sales & Dishes: the week, the forecast as a range, and the dishes in the four corners with the engine's own lines", () => {
  open("sales_dishes");
  expect(within(panel("Sales, last 7 days")).getByText("KES 99,090")).toBeTruthy();
  expect(within(panel("Next 7 days")).getByText(/A range, not a promise/)).toBeTruthy();
  const matrix = panel("Best and weakest dishes");
  expect(within(matrix).getByRole("img").getAttribute("aria-label")).toMatch(/how much each plate earns you/);
  expect(within(matrix).getAllByText(/best dish/i).length).toBeGreaterThan(0);
  const dots = matrix.querySelectorAll("svg circle");
  expect(dots.length).toBe(areas().sales_dishes.blocks.matrix.dishes ? (areas().sales_dishes.blocks.matrix.dishes as unknown[]).length : 0);
  expect(matrix.querySelectorAll("svg line[stroke-dasharray]")).toHaveLength(2);                // the two cut lines the engine drew
});

it("Sales & Dishes: what each dish earns, price ideas with the way they are worth, and the delivery gap in words", () => {
  open("sales_dishes");
  expect(within(panel("What each dish earns")).getByText("Nyama choma (goat)")).toBeTruthy();
  expect(within(panel("What each dish earns")).getByText("KES 61,360")).toBeTruthy();
  expect(panel("Price ideas").textContent).toMatch(/Nyama choma \(goat\).*KES 1,400 → KES 1,500 · about KES 5,900 a month/);
  const delivery = panel("What delivery really pays");
  expect(delivery.textContent).toMatch(/Burger on Glovo: keeps KES 170 a plate instead of KES 320 in the restaurant \(25% commission\)\. It would need KES 800 to keep your floor\./);
  expect(within(delivery).getByText(/Best and weakest hours/)).toBeTruthy();
});

it("Sales & Dishes: the 30-day outlook is a range, win-back counts the regulars, and what-if points at Ask LEVIII", () => {
  open("sales_dishes");
  expect(within(panel("Next 30 days")).getByText(/likely, between KES 348,912 and KES 594,432/)).toBeTruthy();
  expect(within(panel("Winning guests back")).getByText("31")).toBeTruthy();
  expect(within(panel("What if I change a price")).getByRole("link", { name: /Try it/ }).getAttribute("href")).toMatch(/^\/os\?q=What/);
});

// ── Store & Suppliers ────────────────────────────────────────────────────────

it("Store & Suppliers: the item that went missing is named with how much, how far off, and what it is worth", () => {
  open("store");
  const missing = panel("Missing stock");
  expect(within(missing).getByText("Beef")).toBeTruthy();
  expect(within(missing).getByText("34.2% off")).toBeTruthy();
  expect(missing.textContent).toMatch(/Used 9.91 kg; your sales explain 7.38 kg\. That is 2.53 kg more, worth KES 2,021\./);
  expect(within(missing).getByText(/not a finding about anyone/)).toBeTruthy();
  expect(within(panel("Store-to-kitchen handovers")).getByText(/the store said 4 kg, the kitchen counted 3.8 kg/)).toBeTruthy();
  expect(panel("Suppliers").textContent).toMatch(/Kenchic delivered 9.3 of 10 kg of Chicken on 10 Oct — 0.7 kg short, about KES 334\./);
});

it("Store & Suppliers: a healthy store says nothing was missing, in the window it looked at", () => {
  const a = areas().store;
  (a.blocks.missing as unknown as { items: { check: boolean }[] }).items.forEach((i) => { i.check = false; });
  open("store", a);
  expect(within(panel("Missing stock")).getByText(/Nothing was used beyond what your sales explain in the last 7 days/)).toBeTruthy();
});

// ── Cash Check ───────────────────────────────────────────────────────────────

it("Cash Check: each count against the till, the shift to look at flagged, the repeating Tuesday and the dish charged under its price", () => {
  open("cash");
  const shifts = within(panel("Cash count check")).getByRole("table");
  const flagged = within(shifts).getAllByRole("row").filter((r) => r.getAttribute("data-check") === "true");
  expect(flagged.length).toBe(2);
  const patterns = panel("Recurring patterns");
  expect(within(patterns).getByText("4/4")).toBeTruthy();
  expect(patterns.textContent).toMatch(/Tuesday evening: short 4 of the last 4 times, about KES 491 each — KES 1,965 in all\./);
  expect(within(panel("Sold below menu price")).getByText(/Menu KES 300, charged KES 270 — about KES 2,057 a month/)).toBeTruthy();
  const mpesa = areas().cash.blocks.mpesa as unknown as { headline: string };
  expect(within(panel("M-Pesa check")).getByText(mpesa.headline)).toBeTruthy();              // the figures themselves are tested in owner-mpesa.test.tsx
});

// ── Staff ────────────────────────────────────────────────────────────────────

it("Staff: wages against the owner's target, sales per staff hour, overtime, each person and each kitchen station", () => {
  open("staff");
  const wages = panel("Wages");
  expect(within(wages).getByRole("img").getAttribute("aria-label")).toBe("Out of every KES 100, wages: 28.2%, Fine. Your target is 32%.");
  expect(within(wages).getByText("KES 362")).toBeTruthy();
  expect(within(wages).getByRole("list", { name: "Wages by person, last 30 days" })).toBeTruthy();
  expect(within(panel("On shift")).getByText("5")).toBeTruthy();
  const kitchen = panel("Kitchen speed");
  expect(within(kitchen).getByText("Grill")).toBeTruthy();
  expect(kitchen.textContent).toMatch(/Slowest against its own usual: grill \(8 min over\)/);
});

// ── Permits & Settings ───────────────────────────────────────────────────────

it("Permits & Settings: licences with how long they have left, the targets set, the till connection and how complete the costs are", () => {
  open("permits");
  expect(within(panel("Licences")).getByText("Health certificate")).toBeTruthy();
  expect(within(panel("Licences")).getByText("Expires soon")).toBeTruthy();
  expect(within(panel("Your targets")).getByText("2 of 24")).toBeTruthy();
  expect(within(panel("Till connection")).getByText("Recorded here")).toBeTruthy();
  const trust = panel("How complete your costs are");
  expect(within(trust).getByText("100%")).toBeTruthy();
  expect(within(trust).getByRole("progressbar").getAttribute("aria-valuenow")).toBe("100");
  expect(within(trust).getByText(/All 29 dishes have an ingredient cost/)).toBeTruthy();
});

// ── states: a block with nothing says why, and draws nothing ─────────────────

it.each(AREA_KEYS)("%s: a brand-new restaurant sees a reason in every panel and no chart", (key) => {
  const fresh = areas()[key];
  fresh.blocks = Object.fromEntries(Object.entries(fresh.blocks).map(([k, b]) => [k, { state: b.state === "unavailable" ? "unavailable" : "no_data", as_of: null, reason: "Nothing recorded yet.", ...(b.info ? { info: true } : {}) }]));
  open(key, fresh);
  for (const block of Object.keys(fresh.blocks)) {
    const p = panel(BLOCK_TITLES[key][block]);
    if (!(fresh.blocks[block] as { info?: boolean }).info) expect(within(p).getByRole("status").textContent).toMatch(/Nothing recorded yet|Not available/);
  }
  expect(document.querySelector("svg")).toBeNull();
});

it("Cash Check: a young restaurant is told how far along the pattern check is", () => {
  const a = areas().cash;
  a.blocks.patterns = { state: "learning", as_of: "2026-10-15T00:00:00+00:00", day: 9, of: 28, reason: "Needs four weeks of cash counts to spot a repeating pattern." };
  open("cash", a);
  const p = panel("Recurring patterns");
  expect(within(p).getByRole("status").textContent).toMatch(/Learning · day 9 of 28/);
  expect(p.querySelector("table")).toBeNull();
});

it("a panel for an information block (what-if, till connection) carries no data-state chip", () => {
  open("sales_dishes");
  expect(within(panel("What if I change a price")).queryByText("Live")).toBeNull();
});

it("Cash Check: the newest counts show first, a count to look at is never hidden, and the rest are one tap away", () => {
  const a = areas().cash;
  open("cash", a);
  const shifts = panel("Cash count check");
  const total = (a.blocks.shifts as unknown as { shifts: { check: boolean }[] }).shifts;
  const rows = () => within(shifts).getAllByRole("row").slice(1);
  expect(rows().length).toBeLessThan(total.length);
  expect(rows().filter((r) => r.getAttribute("data-check") === "true")).toHaveLength(total.filter((s) => s.check).length);
  fireEvent.click(within(shifts).getByRole("button", { name: `Show all ${total.length} counts` }));
  expect(rows()).toHaveLength(total.length);
  fireEvent.click(within(shifts).getByRole("button", { name: "Show fewer" }));
  expect(rows().length).toBeLessThan(total.length);
});

it("Sales & Dishes: a long list of delivery gaps shows the worst few and says how many more there are", () => {
  open("sales_dishes");
  const delivery = panel("What delivery really pays");
  expect(within(delivery).getAllByText(/to keep your floor/)).toHaveLength(5);
  expect(within(delivery).getByText(/\d+ more dishes lose too much to a delivery app/)).toBeTruthy();
});
