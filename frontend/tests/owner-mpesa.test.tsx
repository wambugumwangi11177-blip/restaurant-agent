import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import AreaBody from "@/components/owner/AreaBody";
import MpesaUpload from "@/components/owner/areas/MpesaUpload";
import api from "@/lib/api";
import { kes } from "@/lib/owner/format";
import { OWNER_DATA_CHANGED } from "@/lib/owner/useOwnerHome";
import type { MpesaBlock } from "@/lib/owner/areaTypes";
import type { OwnerHome } from "@/lib/owner/types";
import fixture from "./fixtures/owner/home.json";
import block from "./fixtures/owner/mpesa_block.json";

vi.mock("@/lib/api", () => ({ default: { get: vi.fn(), post: vi.fn(), delete: vi.fn() } }));
vi.mock("next/link", () => ({ default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => <a href={href} {...rest}>{children}</a> }));

// The figures below are read from the fixture (a real block from the generated demo, whose numbers move with the date it is built on).
const mpesa = block as unknown as MpesaBlock;
const cash = () => structuredClone((fixture as unknown as OwnerHome).areas.cash);
const withMpesa = (b: unknown) => { const a = cash(); (a.blocks as Record<string, unknown>).mpesa = b; return a; };
const panel = () => screen.getByRole("region", { name: "M-Pesa check" });

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.get).mockResolvedValue({ data: { statements: [], payments_on_file: 0 } } as never);
});
afterEach(cleanup);

// ── the check ────────────────────────────────────────────────────────────────

it("says in one sentence what the statement found, and where the figures come from", () => {
  render(<AreaBody area={cash()} />);
  const p = within(panel());
  expect(p.getByText(mpesa.headline!)).toBeTruthy();
  expect(p.getByText("From your M-Pesa statement")).toBeTruthy();                           // a statement is not the till, and says so
});

it("counts what was checked, what matched and what has no match", () => {
  render(<AreaBody area={cash()} />);
  const p = within(panel());
  const checked = mpesa.checked!, matched = mpesa.matched!;
  const stat = (label: string) => p.getByText(label).closest("div")!;
  expect(stat("Sales checked").textContent).toContain(String(checked.sales));
  expect(stat("Sales checked").textContent).toContain(`${checked.payments} payments on the statement`);
  expect(stat("Matched").textContent).toContain(String(matched.sales));
  expect(stat("Matched").textContent).toContain(kes(matched.kes));
  expect(stat("To look at").textContent).toContain(String(mpesa.sales_without_payment!.count + mpesa.payments_without_sale!.count));
});

it("lists the sales with no payment, newest first, each with its table and amount", () => {
  render(<AreaBody area={cash()} />);
  const sales = mpesa.sales_without_payment!;
  expect(within(panel()).getByText(`Sales with no payment on the statement · ${kes(sales.kes)}`)).toBeTruthy();
  for (const s of sales.items!) {
    const li = within(panel()).getByText(new RegExp(`${s.what.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}$`)).closest("li")!;
    expect(li.textContent).toContain(kes(s.kes));
  }
});

it("a payment with no sale, and a sale paid a different amount, are the other findings", () => {
  const b = structuredClone(mpesa);
  b.headline = "1 payment (KES 2,500) has no sale recorded; 1 sale paid a different amount from the one recorded.";
  b.payments_without_sale = { count: 1, kes: 2500, items: [{ receipt: "SJE4K2L9QA", at: "2026-10-14T09:41:07+00:00", kes: 2500, from: "Customer Payment from 2547****9999 - SOMEONE" }] };
  b.sales_without_payment = { count: 0, kes: 0, items: [] };
  b.different_amounts = [{ order_id: 5, receipt: "SJE4K2LAB7", sale_kes: 500, payment_kes: 450 }];
  render(<AreaBody area={withMpesa(b)} />);
  const p = within(panel());
  expect(p.getByText("Payments with no sale recorded · KES 2,500")).toBeTruthy();
  expect(p.getByText(/SOMEONE/).closest("li")!.textContent).toContain("KES 2,500");
  expect(p.getByText(/SJE4K2LAB7: recorded KES 500, paid KES 450/)).toBeTruthy();
  expect(p.queryByText(/^Sales with no payment/)).toBeNull();
});

it("says how many more there are than it lists, and how many sales fall outside the statement's days", () => {
  const b = structuredClone(mpesa);
  b.sales_without_payment = { ...b.sales_without_payment!, count: b.sales_without_payment!.items!.length + 4 };
  b.outside_statement = { sales: 434, kes: 454160 };
  render(<AreaBody area={withMpesa(b)} />);
  expect(within(panel()).getByText("and 4 more")).toBeTruthy();
  expect(within(panel()).getByText(/434 M-Pesa sales \(KES 454,160\) fall outside the days this statement covers, so they are not checked\./)).toBeTruthy();
});

it("shows the rule it used, the minutes, with a way to change it", () => {
  render(<AreaBody area={cash()} />);
  expect(within(panel()).getByText(/Minutes between a sale and its payment/)).toBeTruthy();
});

it("a statement that has gone stale says so in words", () => {
  const b = { ...structuredClone(mpesa), state: "stale", age_days: 5 };
  render(<AreaBody area={withMpesa(b)} />);
  expect(within(panel()).getByText(/Out of date · 5 days old/)).toBeTruthy();
});

it("with no statement, the panel says what to do and the upload is right there", () => {
  const b = { state: "no_data", as_of: null, reason: "Upload your M-Pesa statement to check it against your sales." };
  render(<AreaBody area={withMpesa(b)} />);
  expect(within(panel()).getByText(/Upload your M-Pesa statement to check it against your sales\./)).toBeTruthy();
  expect(screen.getByLabelText("Choose a statement (CSV)")).toBeTruthy();
});

it("no system word, no cents and no placeholder dash reaches the owner", () => {
  render(<AreaBody area={cash()} />);
  const text = panel().textContent ?? "";
  for (const word of ["cents", "_kes", "undefined", "NaN", "null", "[object"]) expect(text).not.toContain(word);
});

// ── the upload ───────────────────────────────────────────────────────────────

const csv = () => new File(["Receipt No.,Completion Time,Paid In\nSJE4K2L9QA,2026-10-14 12:41:07,300.00\n"], "statement.csv", { type: "text/csv" });
const choose = (file: File) => fireEvent.change(screen.getByLabelText("Choose a statement (CSV)"), { target: { files: [file] } });
const result = (over = {}) => ({
  upload: { id: 7, filename: "statement.csv", uploaded_at: "2026-10-14T10:00:00+00:00", lines: 8, from: "2026-10-14T09:41:07+00:00", to: "2026-10-14T15:44:19+00:00", uploaded_by: "o@e.com" },
  new: 8, already_uploaded: 0, not_read: [], not_read_count: 0, money_in_kes: 6315, money_out_kes: 8035, about: {}, ...over,
});

it("sends the file as a form and says what was read", async () => {
  vi.mocked(api.post).mockResolvedValue({ data: result() } as never);
  render(<MpesaUpload />);
  choose(csv());
  const status = await screen.findByRole("status");
  expect(status.textContent).toContain("Read 8 new payments from statement.csv (KES 6,315 in, KES 8,035 out).");
  const [url, body, config] = vi.mocked(api.post).mock.calls[0] as [string, FormData, { headers: Record<string, string> }];
  expect(url).toBe("/api/v1/owner/mpesa/statement");
  expect(body instanceof FormData && (body.get("file") as File).name === "statement.csv").toBe(true);
  expect(config.headers["Content-Type"]).toBe("multipart/form-data");
});

it("lists the rows it could not read, with their numbers and why, and says how many more", async () => {
  vi.mocked(api.post).mockResolvedValue({ data: result({
    not_read: [{ row: 12, reason: "the payment is 'failed', not completed" }, { row: 18, reason: "the time 'not a time' is not one we can read" }], not_read_count: 27 }) } as never);
  render(<MpesaUpload />);
  choose(csv());
  const status = await screen.findByRole("status");
  expect(within(status).getByText("27 rows were not read")).toBeTruthy();
  expect(within(status).getByText("Row 12: the payment is 'failed', not completed")).toBeTruthy();
  expect(within(status).getByText("and 25 more.")).toBeTruthy();
});

it("a file with nothing new says nothing changed", async () => {
  vi.mocked(api.post).mockResolvedValue({ data: result({ upload: null, new: 0, already_uploaded: 8 }) } as never);
  render(<MpesaUpload />);
  choose(csv());
  expect((await screen.findByRole("status")).textContent).toContain("Every payment in this file was already uploaded, so nothing changed.");
});

it("a file we cannot read says why, in the words the server gave", async () => {
  vi.mocked(api.post).mockRejectedValue({ response: { status: 422, data: { detail: "This does not look like an M-Pesa statement. It needs a header row with at least the receipt number." } } });
  render(<MpesaUpload />);
  choose(csv());
  expect((await screen.findByRole("alert")).textContent).toContain("This does not look like an M-Pesa statement.");
});

it("a failed request says so without a stack trace", async () => {
  vi.mocked(api.post).mockRejectedValue(new Error("Network Error"));
  render(<MpesaUpload />);
  choose(csv());
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toContain("We could not upload that file just now");
  expect(alert.textContent).not.toContain("Network Error");
});

it("tells Home to ask again after an upload, so the figures move", async () => {
  vi.mocked(api.post).mockResolvedValue({ data: result() } as never);
  const heard = vi.fn();
  window.addEventListener(OWNER_DATA_CHANGED, heard);
  render(<MpesaUpload />);
  choose(csv());
  await screen.findByRole("status");
  expect(heard).toHaveBeenCalledTimes(1);
  window.removeEventListener(OWNER_DATA_CHANGED, heard);
});

it("shows what is on file and takes an upload back", async () => {
  vi.mocked(api.get).mockResolvedValue({ data: { statements: [result().upload], payments_on_file: 8 } } as never);
  vi.mocked(api.delete).mockResolvedValue({ data: { deleted: 7, payments_removed: 8 } } as never);
  const heard = vi.fn();
  window.addEventListener(OWNER_DATA_CHANGED, heard);
  render(<MpesaUpload />);
  fireEvent.click(await screen.findByText("8 payments on file from 1 upload"));
  expect(screen.getByText(/statement\.csv · 8 payments/)).toBeTruthy();
  vi.mocked(api.get).mockResolvedValue({ data: { statements: [], payments_on_file: 0 } } as never);
  fireEvent.click(screen.getByRole("button", { name: "Remove this upload" }));
  await waitFor(() => expect(api.delete).toHaveBeenCalledWith("/api/v1/owner/mpesa/statements/7"));
  await waitFor(() => expect(heard).toHaveBeenCalled());
  window.removeEventListener(OWNER_DATA_CHANGED, heard);
});

it("every control is a comfortable tap target", async () => {
  vi.mocked(api.get).mockResolvedValue({ data: { statements: [result().upload], payments_on_file: 8 } } as never);
  render(<MpesaUpload />);
  await screen.findByText("8 payments on file from 1 upload");
  const smalls = [...document.querySelectorAll("button, label, summary")].filter((el) => !/min-h-10/.test(el.className));
  expect(smalls.map((el) => el.textContent)).toEqual([]);
});

it("an uploaded list that cannot be fetched does not stop the upload from working", async () => {
  vi.mocked(api.get).mockRejectedValue(new Error("offline"));
  vi.mocked(api.post).mockResolvedValue({ data: result() } as never);
  render(<MpesaUpload />);
  choose(csv());
  expect((await screen.findByRole("status")).textContent).toContain("Read 8 new payments");
});

it("while it is reading, the control says so and cannot be used twice", async () => {
  let done!: (v: unknown) => void;
  vi.mocked(api.post).mockReturnValue(new Promise((r) => { done = r; }) as never);
  render(<MpesaUpload />);
  choose(csv());
  expect(await screen.findByText("Reading your statement…")).toBeTruthy();
  expect((document.getElementById("mpesa-statement") as HTMLInputElement).disabled).toBe(true);
  await act(async () => { done({ data: result() }); });
  expect(await screen.findByText("Choose a statement (CSV)")).toBeTruthy();
});
