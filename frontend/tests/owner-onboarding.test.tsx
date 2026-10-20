import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import HomePage from "../src/app/(owner)/home/page";
import SettingsProvider, { SETTINGS_CHANGED } from "@/components/owner/settings/SettingsProvider";
import TargetsOnboarding from "@/components/owner/home/TargetsOnboarding";
import { FIRST_WEEK_ORDER, lockedAreas, unlockedAreas } from "@/components/owner/home/FirstWeek";
import api from "@/lib/api";
import settings from "./fixtures/owner/settings.json";
import home from "./fixtures/owner/home.json";
import fresh from "./fixtures/owner/home_fresh.json";
import { HEADLINE_SETTINGS, type SettingsPayload } from "@/lib/owner/settings";
import type { OwnerHome } from "@/lib/owner/types";

vi.mock("@/lib/api", () => ({ default: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => ({ user: { restaurant_name: "Mama Oliech", tenant_name: "Mama Oliech" } }) }));
vi.mock("next/link", () => ({ default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => <a href={href} {...rest}>{children}</a> }));

const settingsPayload = () => structuredClone(settings) as unknown as SettingsPayload;
const homeAt = (age: number, chosen = true): OwnerHome => ({ ...(structuredClone(home) as unknown as OwnerHome), setup: { targets_chosen: chosen, age_days: age } });
const serve = (h: OwnerHome) => vi.mocked(api.get).mockImplementation(async (url: string) => ({ data: url.includes("/owner/settings") ? settingsPayload() : h }) as never);

beforeEach(() => { vi.clearAllMocks(); window.localStorage.clear(); window.location.hash = ""; });
afterEach(cleanup);

// ── the first-week rule ──────────────────────────────────────────────────────

it("one more panel opens every day, in the order a new restaurant has something to say, and all of them after the week", () => {
  expect([...unlockedAreas(0)]).toEqual(["permits"]);
  expect([...unlockedAreas(1)]).toEqual(["permits", "money"]);
  expect([...unlockedAreas(4)]).toEqual(["permits", "money", "store", "sales_dishes", "cash"]);
  expect(unlockedAreas(5).size).toBe(6);
  expect(unlockedAreas(400).size).toBe(6);
  expect(unlockedAreas(-3).size).toBe(1);
  expect(lockedAreas(1)).toEqual({ store: 3, sales_dishes: 4, cash: 5, staff: 6 });
  expect(lockedAreas(5)).toEqual({});
  expect(FIRST_WEEK_ORDER).toHaveLength(6);
});

// ── "Your targets" ───────────────────────────────────────────────────────────

function renderTargets(chosen: boolean) {
  vi.mocked(api.get).mockResolvedValue({ data: settingsPayload() } as never);
  return render(<SettingsProvider><TargetsOnboarding restaurantId={7} chosen={chosen} /></SettingsProvider>);
}

it("a new owner is asked their targets once, with the usual answers filled in, and every one is saved", async () => {
  renderTargets(false);
  fireEvent.click(await screen.findByRole("button", { name: "Set my targets" }));
  const dialog = screen.getByRole("dialog", { name: "Your targets" });
  expect(within(dialog).getAllByRole("slider")).toHaveLength(HEADLINE_SETTINGS.length);
  expect(within(dialog).getByText("Out of every KES 100 you sell, how much should ingredients cost at most?")).toBeTruthy();
  expect((within(dialog).getAllByRole("spinbutton")[0] as HTMLInputElement).value).toBe("35");              // the usual answer
  vi.mocked(api.put).mockResolvedValue({ data: { ...settingsPayload(), chosen: true } } as never);
  fireEvent.click(within(dialog).getByRole("button", { name: "These are right" }));
  await waitFor(() => expect(api.put).toHaveBeenCalledTimes(1));
  const [url, body] = vi.mocked(api.put).mock.calls[0];
  expect(url).toBe("/api/v1/owner/settings");
  expect(Object.keys(body as object).sort()).toEqual([...HEADLINE_SETTINGS].sort());                         // even the ones left as they were: that is what records the choice
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
});

it("an owner can change an answer before saving, and 'Not now' on the sheet saves nothing", async () => {
  renderTargets(false);
  fireEvent.click(await screen.findByRole("button", { name: "Set my targets" }));
  const dialog = screen.getByRole("dialog");
  fireEvent.change(within(dialog).getAllByRole("spinbutton")[0], { target: { value: "30" } });
  vi.mocked(api.put).mockResolvedValue({ data: settingsPayload() } as never);
  fireEvent.click(within(dialog).getByRole("button", { name: "These are right" }));
  await waitFor(() => expect(api.put).toHaveBeenCalled());
  expect((vi.mocked(api.put).mock.calls[0][1] as Record<string, number>).food_cost_target_pct).toBe(30);
  cleanup();
  vi.clearAllMocks();
  renderTargets(false);
  fireEvent.click(await screen.findByRole("button", { name: "Set my targets" }));
  fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Not now" }));
  expect(api.put).not.toHaveBeenCalled();
});

it("once the targets are chosen the step is gone; 'Not now' hides it for today and it comes back tomorrow", async () => {
  const { unmount } = renderTargets(true);
  await waitFor(() => expect(api.get).toHaveBeenCalled());
  expect(screen.queryByRole("heading", { name: "Set your targets" })).toBeNull();
  unmount();
  const second = renderTargets(false);
  fireEvent.click(await screen.findByRole("button", { name: "Not now" }));
  expect(screen.queryByRole("heading", { name: "Set your targets" })).toBeNull();
  second.unmount();
  renderTargets(false);
  await waitFor(() => expect(api.get).toHaveBeenCalled());
  expect(screen.queryByRole("heading", { name: "Set your targets" })).toBeNull();                              // still hidden today
  cleanup();
  window.localStorage.setItem("owner.targets.later.7", "Mon Jan 01 2001");
  renderTargets(false);
  expect(await screen.findByRole("heading", { name: "Set your targets" })).toBeTruthy();                       // a different day: asked again
});

it("a browser that blocks storage never breaks Home: the step simply shows", async () => {
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
  renderTargets(false);
  fireEvent.click(await screen.findByRole("button", { name: "Not now" }));
  expect(screen.queryByRole("heading", { name: "Set your targets" })).toBeNull();                              // hidden until the page is reloaded
  vi.restoreAllMocks();
});

// ── Home: the first week and the first questions ─────────────────────────────

it("a brand-new restaurant's Home asks for its targets and opens one panel", async () => {
  serve({ ...(structuredClone(fresh) as unknown as OwnerHome) });
  render(<SettingsProvider><HomePage /></SettingsProvider>);
  expect(await screen.findByRole("heading", { name: "Set your targets" })).toBeTruthy();
  expect(screen.getByText(/day 1 of 6/)).toBeTruthy();
  expect(screen.getByRole("button", { name: /Permits & Settings/ })).toBeTruthy();
  for (const name of ["My Money", "Sales & Dishes", "Store & Suppliers", "Cash Check", "Staff"]) expect(screen.queryByRole("button", { name: new RegExp(name) })).toBeNull();
  expect(screen.getByRole("region", { name: "My Money, opens on day 2" }).textContent).toContain("Opens on day 2 of your first week");
});

it("on day 2 two panels are open and the rest say when they open; a locked panel cannot be opened by a link", async () => {
  window.location.hash = "#area-cash";
  serve(homeAt(1));
  render(<SettingsProvider><HomePage /></SettingsProvider>);
  expect(await screen.findByText(/day 2 of 6/)).toBeTruthy();
  expect(screen.getAllByRole("button", { name: /Permits & Settings|My Money/ })).toHaveLength(2);
  expect(screen.getByRole("region", { name: "Cash Check, opens on day 5" })).toBeTruthy();
  expect(screen.queryByRole("region", { name: "Cash Check" })).toBeNull();
});

it("'Open everything now' opens all six, removes the banner, and is remembered", async () => {
  serve(homeAt(1));
  const first = render(<SettingsProvider><HomePage /></SettingsProvider>);
  fireEvent.click(await screen.findByRole("button", { name: "Open everything now" }));
  expect(screen.getAllByRole("button", { name: /Permits & Settings|My Money|Store & Suppliers|Sales & Dishes|Cash Check|Staff/ }).length).toBeGreaterThanOrEqual(6);
  expect(screen.queryByText(/Your first week/)).toBeNull();
  first.unmount();
  render(<SettingsProvider><HomePage /></SettingsProvider>);
  await screen.findByTestId("sales-today");
  expect(screen.queryByText(/Your first week/)).toBeNull();
  expect(screen.getByRole("button", { name: /Cash Check/ })).toBeTruthy();
});

it("after the first week, and for an established restaurant, nothing is locked and there is no banner", async () => {
  for (const age of [5, 400]) {
    serve(homeAt(age));
    const { unmount } = render(<SettingsProvider><HomePage /></SettingsProvider>);
    await screen.findByTestId("sales-today");
    expect(screen.queryByText(/Your first week/)).toBeNull();
    expect(screen.getByRole("button", { name: /Staff/ })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Set your targets" })).toBeNull();
    unmount();
  }
});

it("saving a setting makes Home ask again: every card and figure may have moved", async () => {
  serve(homeAt(400));
  render(<SettingsProvider><HomePage /></SettingsProvider>);
  await screen.findByTestId("sales-today");
  const calls = () => vi.mocked(api.get).mock.calls.filter(([u]) => String(u).endsWith("/owner/home")).length;
  const before = calls();
  await act(async () => { window.dispatchEvent(new Event(SETTINGS_CHANGED)); });
  await waitFor(() => expect(calls()).toBe(before + 1));
});
