import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import AssumptionChip from "@/components/owner/settings/AssumptionChip";
import SettingsProvider, { SETTINGS_CHANGED } from "@/components/owner/settings/SettingsProvider";
import AreaBody from "@/components/owner/AreaBody";
import api from "@/lib/api";
import home from "./fixtures/owner/home.json";
import type { OwnerHome } from "@/lib/owner/types";
import settings from "./fixtures/owner/settings.json";
import type { SettingsPayload, SettingsPreview } from "@/lib/owner/settings";

vi.mock("@/lib/api", () => ({ default: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }));

const payload = () => structuredClone(settings) as unknown as SettingsPayload;
const floorChip = { setting: "margin_floor_pct", value: 40, label: "Lowest share you keep" };
const preview = (over: Partial<SettingsPreview> = {}): SettingsPreview => ({
  changes: [{ key: "margin_floor_pct", label: "Lowest share you keep on a dish", unit: "%", from: 40, to: 30 }],
  cards_now: 9, cards_after: 8, appear: [], disappear: ["Reprice: set Quarter chicken to KES 435 (from KES 400)"], figures: ["Raise Burger on Glovo to KES 700 (from KES 600)"], changed: 2, ...over,
});

function setup(chip = floorChip) {
  vi.mocked(api.get).mockResolvedValue({ data: payload() } as never);
  render(<SettingsProvider><AssumptionChip assumption={chip} /></SettingsProvider>);
}
async function openSheet(label = "Lowest share you keep") {
  fireEvent.click(await screen.findByRole("button", { name: `Change ${label}` }));
  return screen.getByRole("dialog");
}
const number = (dialog: HTMLElement) => within(dialog).getByRole("spinbutton") as HTMLInputElement;
const type = (el: HTMLInputElement, v: number | string) => fireEvent.change(el, { target: { value: String(v) } });

beforeEach(() => { vi.clearAllMocks(); });
afterEach(cleanup);
const later = (ms: number) => act(async () => { await new Promise((r) => setTimeout(r, ms)); });      // the sheet waits for the slider to stop before it asks

// ── the chip ─────────────────────────────────────────────────────────────────

it("says the rule a number rests on, in the unit it was asked in, with a way to change it", async () => {
  setup();
  const chip = await screen.findByTestId("based-on");
  expect(chip.textContent).toBe("Based on: Lowest share you keep 40%· Change");
  expect(screen.getByRole("button", { name: "Change Lowest share you keep" })).toBeTruthy();
});

it("when the settings cannot be read the rule is still said, and no Change is offered", async () => {
  vi.mocked(api.get).mockRejectedValue(new Error("blocked"));
  render(<SettingsProvider><AssumptionChip assumption={floorChip} /></SettingsProvider>);
  expect((await screen.findByTestId("based-on")).textContent).toBe("Based on: Lowest share you keep 40");
  expect(screen.queryByRole("button")).toBeNull();
});

// ── the sheet for one setting ────────────────────────────────────────────────

it("opens on that setting: its question, a slider and a number bound by the allowed range, and the usual answer", async () => {
  setup();
  const dialog = await openSheet();
  expect(within(dialog).getByText("What is the lowest share of a dish's price you are willing to keep after its ingredients?")).toBeTruthy();
  const slider = within(dialog).getByRole("slider") as HTMLInputElement;
  expect([slider.min, slider.max, slider.step, slider.value]).toEqual(["20", "70", "1", "40"]);
  expect([number(dialog).min, number(dialog).max]).toEqual(["20", "70"]);
  expect(within(dialog).getByText("Allowed: 20% to 70%")).toBeTruthy();
  expect(document.activeElement).toBe(number(dialog));
  expect((within(dialog).getByRole("button", { name: "Save" }) as HTMLButtonElement).disabled).toBe(true);        // nothing to save yet
});

it("as the slider moves it asks the engines what would change on Home — once, after the owner stops", async () => {
  setup();
  vi.mocked(api.post).mockResolvedValue({ data: preview() } as never);
  const dialog = await openSheet();
  type(number(dialog), 35);
  await later(120);
  expect(api.post).not.toHaveBeenCalled();                                                  // still moving: it waits for the slider to stop
  type(number(dialog), 30);
  await later(450);
  expect(api.post).toHaveBeenCalledTimes(1);
  expect(api.post).toHaveBeenCalledWith("/api/v1/owner/settings/preview", { margin_floor_pct: 30 });
  const line = await within(dialog).findByText(/2 cards on Home would change/);
  expect(line.textContent).toBe("2 cards on Home would change: 1 would go away, 1 would change its figure.");
  expect(within(dialog).getByText("Reprice: set Quarter chicken to KES 435 (from KES 400)")).toBeTruthy();
});

it("says so when nothing would change, and when it cannot check", async () => {
  setup();
  vi.mocked(api.post).mockResolvedValueOnce({ data: preview({ changed: 0, appear: [], disappear: [], figures: [], cards_after: 9 }) } as never);
  const dialog = await openSheet();
  type(number(dialog), 41);
  await later(450);
  expect(await within(dialog).findByText("Nothing on Home would change.")).toBeTruthy();
  vi.mocked(api.post).mockRejectedValueOnce(new Error("slow"));
  type(number(dialog), 42);
  await later(450);
  expect(await within(dialog).findByText(/could not check that just now/)).toBeTruthy();
});

it("an answer to a position the slider has already left is ignored", async () => {
  setup();
  let first!: (v: unknown) => void;
  vi.mocked(api.post).mockImplementationOnce(() => new Promise((r) => { first = r; }) as never).mockResolvedValueOnce({ data: preview({ changed: 7, disappear: [], figures: [], appear: ["new"] }) } as never);
  const dialog = await openSheet();
  type(number(dialog), 30);
  await later(450);
  type(number(dialog), 25);
  await later(450);
  await act(async () => { first({ data: preview({ changed: 1 }) }); });
  expect(await within(dialog).findByText(/7 cards on Home would change/)).toBeTruthy();
  expect(within(dialog).queryByText(/1 card on Home would change/)).toBeNull();
});

it("a number outside the allowed range is refused on the sheet: no preview, no save, and it says why", async () => {
  setup();
  const dialog = await openSheet();
  type(number(dialog), 99);
  expect(within(dialog).getByRole("alert").textContent).toBe("Choose a number from 20 to 70.");
  expect((within(dialog).getByRole("button", { name: "Save" }) as HTMLButtonElement).disabled).toBe(true);
  await later(500);
  expect(api.post).not.toHaveBeenCalled();
  type(number(dialog), "");
  expect((within(dialog).getByRole("button", { name: "Save" }) as HTMLButtonElement).disabled).toBe(true);
});

it("'Use our usual' puts the default back", async () => {
  setup();
  const dialog = await openSheet();
  type(number(dialog), 55);
  fireEvent.click(within(dialog).getByRole("button", { name: "Use our usual: 40%" }));
  expect(number(dialog).value).toBe("40");
  expect(within(dialog).queryByRole("button", { name: /Use our usual/ })).toBeNull();
});

it("saving sends only what changed, closes the sheet and tells Home to look again", async () => {
  setup();
  const next = payload();
  next.fields = next.fields.map((f) => (f.key === "margin_floor_pct" ? { ...f, value: 30, is_default: false } : f));
  vi.mocked(api.post).mockResolvedValue({ data: preview() } as never);
  vi.mocked(api.put).mockResolvedValue({ data: next } as never);
  const heard = vi.fn();
  window.addEventListener(SETTINGS_CHANGED, heard);
  const dialog = await openSheet();
  type(number(dialog), 30);
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
  await waitFor(() => expect(api.put).toHaveBeenCalledWith("/api/v1/owner/settings", { margin_floor_pct: 30 }));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(heard).toHaveBeenCalledTimes(1);
  window.removeEventListener(SETTINGS_CHANGED, heard);
  expect(screen.getByTestId("based-on").textContent).toContain("Lowest share you keep 40%");        // the chip shows what the card was built on until Home reloads
  fireEvent.click(screen.getByRole("button", { name: "Change Lowest share you keep" }));
  expect(number(screen.getByRole("dialog")).value).toBe("30");                                      // and the sheet now opens on the saved value
});

it("a refusal from the server is shown in its own words and nothing closes", async () => {
  setup();
  vi.mocked(api.post).mockResolvedValue({ data: preview() } as never);
  vi.mocked(api.put).mockRejectedValue({ response: { data: { detail: { field: "margin_floor_pct", message: "margin_floor_pct (60%) cannot be higher than margin_target_pct (55%)." } } } });
  const dialog = await openSheet();
  type(number(dialog), 60);
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
  expect((await within(dialog).findByText(/cannot be higher than margin_target_pct/)).textContent).toContain("55%");
  expect(screen.getByRole("dialog")).toBeTruthy();
});

it("Escape, the close button and a tap outside close it without saving", async () => {
  setup();
  for (const close of [() => fireEvent.keyDown(window, { key: "Escape" }), () => fireEvent.click(screen.getByRole("button", { name: "Close" })), () => fireEvent.click(screen.getByRole("dialog").parentElement!)]) {
    await openSheet();
    close();
    expect(screen.queryByRole("dialog")).toBeNull();
  }
  expect(api.put).not.toHaveBeenCalled();
});

it("it is a real dialog: named, modal, and the first field has focus", async () => {
  setup();
  const dialog = await openSheet();
  expect(dialog.getAttribute("aria-modal")).toBe("true");
  expect(dialog.getAttribute("aria-labelledby")).toBe("settings-title");
  expect(within(dialog).getByRole("heading", { name: "Lowest share you keep on a dish" })).toBeTruthy();
});

it("the Permits & Settings panel says how many targets are set and lets the owner review them all", async () => {
  vi.mocked(api.get).mockResolvedValue({ data: payload() } as never);
  const permits = (structuredClone(home) as unknown as OwnerHome).areas.permits;
  const { unmount } = render(<AreaBody area={permits} />);                                          // no settings to read: nothing to open
  expect(screen.queryByRole("button", { name: /Review my targets/ })).toBeNull();
  unmount();
  render(<SettingsProvider><AreaBody area={permits} /></SettingsProvider>);
  fireEvent.click(await screen.findByRole("button", { name: /Review my targets/ }));
  expect(screen.getByRole("dialog", { name: "Your targets" })).toBeTruthy();
});
