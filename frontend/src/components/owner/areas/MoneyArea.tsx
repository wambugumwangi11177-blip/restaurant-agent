"use client";
import { FormEvent, useState } from "react";
import { Download } from "lucide-react";
import api from "@/lib/api";
import { OWNER_DATA_CHANGED } from "@/lib/owner/useOwnerHome";
import CashRunway from "@/components/charts/CashRunway";
import BreakEvenClock from "@/components/charts/BreakEvenClock";
import BreakEvenLine from "@/components/charts/BreakEvenLine";
import Dial from "@/components/charts/Dial";
import StackedBar from "@/components/charts/StackedBar";
import Waterfall, { type Step } from "@/components/charts/Waterfall";
import { BLOCK_TITLES } from "@/lib/owner/blocks";
import { kes, pct, plural, shortDay } from "@/lib/owner/format";
import type { BillsBlock, BreakEvenBlock, CostDialsBlock, PnlBlock, SavingsBlock, SpikesBlock } from "@/lib/owner/areaTypes";
import type { Area } from "@/lib/owner/types";
import { BlockFrame, Empty, Grid, Note, Pill, Stat } from "./ui";

const T = BLOCK_TITLES.money;
const tone = (word: string) => (word === "Fine" ? "good" : word === "Watch" ? "warn" : "bad") as "good" | "warn" | "bad";

export default function MoneyArea({ area }: { area: Area }) {
  const b = area.blocks;
  return (
    <div className="space-y-3">
      <Pnl block={b.pnl as PnlBlock} />
      <div className="grid gap-3 md:grid-cols-2">
        <Dials block={b.cost_dials as CostDialsBlock} />
        <Clock block={b.breakeven as BreakEvenBlock} />
      </div>
      <Bills block={b.bills as BillsBlock} />
      <div className="grid gap-3 md:grid-cols-2">
        <Spikes block={b.spikes as SpikesBlock} />
        <Savings block={b.savings as SavingsBlock} />
      </div>
    </div>
  );
}

export function Pnl({ block }: { block: PnlBlock }) {
  const line = (key: string) => block.lines?.find((l) => l.key === key);
  const steps: Step[] = block.lines
    ? [
        { key: "sales", label: "Sales", value: line("sales")!.kes, kind: "start", valueLabel: kes(line("sales")!.kes) },
        { key: "ingredients", label: "Ingredients", value: -line("ingredients")!.kes, kind: "minus", valueLabel: kes(-line("ingredients")!.kes) },
        { key: "left", label: "Left after ingredients", value: line("left_after_ingredients")!.kes, kind: "subtotal", valueLabel: kes(line("left_after_ingredients")!.kes) },
        { key: "wages", label: "Wages", value: -line("wages")!.kes, kind: "minus", valueLabel: kes(-line("wages")!.kes) },
        { key: "other", label: "Other costs", value: -line("other_costs")!.kes, kind: "minus", valueLabel: kes(-line("other_costs")!.kes) },
        { key: "kept", label: "What you kept", value: line("kept")!.kes, kind: "end", valueLabel: kes(line("kept")!.kes) },
      ]
    : [];
  const share = block.out_of_every_100;
  // A cost entered nowhere is not a cost of nothing: the block says so in `reason` and keeps the lines it does know.
  const hasLines = block.lines?.some((l) => l.kes !== 0);
  return (
    <BlockFrame title={T.pnl} block={hasLines ? { ...block, state: block.state === "no_data" ? "as_entered" : block.state } : block}>{() => (<>
      {block.state === "no_data" && block.reason && <p role="status" className="mb-3 rounded-md bg-[hsl(38_80%_44%_/_0.1)] px-3 py-2 text-xs text-[var(--v-warn)]">{String(block.reason)}</p>}
      {block.period && <p className="mb-3 text-xs font-semibold">{block.period.label}</p>}
      <Waterfall label="Sales down to what you kept" steps={steps} />
      {share && share.kept != null && (
        <div className="mt-4">
          <p className="mb-1.5 text-[11px] font-bold">Out of every KES 100 you take</p>
          <StackedBar label="Out of every KES 100 you take" segments={[
            { key: "i", label: "Ingredients", value: share.ingredients ?? 0, color: "var(--v-primary)" },
            { key: "w", label: "Wages", value: share.wages ?? 0, color: "var(--v-sidebar-primary)" },
            { key: "o", label: "Other costs", value: share.other_costs ?? 0, color: "var(--v-muted-foreground)" },
            { key: "k", label: "What you kept", value: share.kept ?? 0, color: "var(--v-good)" },
          ]} />
          <ul className="mt-3 space-y-1 text-[11px] leading-relaxed">
            <li>Ingredients = {share.ingredients == null ? "not in yet" : pct(share.ingredients)} of sales.</li>
            <li>Wages = {share.wages == null ? "not in yet" : pct(share.wages)} of sales.</li>
            <li>Ingredients + wages = {share.ingredients == null || share.wages == null ? "not in yet" : pct(share.ingredients + share.wages)} of sales.</li>
          </ul>
        </div>
      )}
      {block.sections?.length > 0 && (
        <details className="mt-4">
          <summary className="flex min-h-10 cursor-pointer items-center text-[11px] font-bold">Where the other costs went</summary>
          <ul className="mt-2 space-y-2">
            {block.sections.map((s) => (
              <li key={s.key} className="text-xs">
                <div className="flex justify-between font-semibold"><span>{s.name}</span><span className="tabular-nums">{kes(s.kes)}</span></div>
                <ul className="mt-0.5 space-y-0.5 pl-3 text-[var(--v-muted-foreground)]">
                  {s.lines.map((l) => (
                    <li key={l.key} className="flex justify-between gap-3">
                      <span>{l.name}{l.basis === "estimated" ? " (estimated)" : ""}{l.is_fixed ? " · fixed" : ""}</span>
                      <span className="tabular-nums">{kes(l.kes)}</span>
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        </details>
      )}
      {block.notes?.map((n) => <Note key={n}>{n}</Note>)}
      {hasLines && block.period && <ExportButtons start={block.period.start} />}
    </>)}</BlockFrame>
  );
}

/** The accountant's file: the month's P&L as Excel or PDF, the same figures as the report. */
export function ExportButtons({ start }: { start: string }) {
  const [busy, setBusy] = useState<"xlsx" | "pdf" | null>(null);
  const [failed, setFailed] = useState(false);
  const month = start.slice(0, 7);
  const get = async (format: "xlsx" | "pdf") => {
    setBusy(format);
    setFailed(false);
    try {
      const res = await api.get<Blob>("/api/v1/owner/money/pnl/export", { params: { month, format }, responseType: "blob", timeout: 60000 });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `profit-and-loss-${month}.${format}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      setFailed(true);
    } finally {
      setBusy(null);
    }
  };
  return (
    <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-[var(--v-border)] pt-3">
      <span className="text-[11px] font-bold">For your accountant</span>
      {(["xlsx", "pdf"] as const).map((f) => (
        <button key={f} type="button" disabled={busy !== null} onClick={() => get(f)}
          className="inline-flex min-h-10 items-center gap-1.5 rounded-lg border border-[var(--v-border)] px-3 text-[11px] font-bold hover:bg-[var(--v-muted)] disabled:opacity-60">
          <Download size={13} aria-hidden />{busy === f ? "Preparing…" : f === "xlsx" ? "Excel" : "PDF"}
        </button>
      ))}
      {failed && <span role="alert" className="text-[11px] text-[var(--v-warn)]">The file could not be made. Please try again.</span>}
    </div>
  );
}

function Dials({ block }: { block: CostDialsBlock }) {
  return (
    <BlockFrame title={T.cost_dials} block={block}>{() => (<>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        <Dial value={block.food_cost_pct} target={block.food_cost_target_pct} label="Out of every KES 100, ingredients" word={block.food_cost_word} tone={tone(block.food_cost_word)} />
        {block.wages_pct == null || block.wages_word == null
          ? <p className="self-center text-xs text-[var(--v-muted-foreground)]">Wages are not in yet.</p>
          : <Dial value={block.wages_pct} target={block.wages_target_pct} label="Out of every KES 100, wages" word={block.wages_word} tone={tone(block.wages_word)} />}
        {block.prime_cost_pct == null || block.prime_cost_word == null || block.prime_cost_target_pct == null
          ? <p className="self-center text-xs text-[var(--v-muted-foreground)]">Ingredients + wages waits until wages are in.</p>
          : <Dial value={block.prime_cost_pct} target={block.prime_cost_target_pct} label="Out of every KES 100, ingredients and wages" word={block.prime_cost_word} tone={tone(block.prime_cost_word)} />}
      </div>
    </>)}</BlockFrame>
  );
}

function Clock({ block }: { block: BreakEvenBlock }) {
  return (
    <BlockFrame title={T.breakeven} block={block}>{() => (<>
      <BreakEvenClock label="Costs covered" breakEven={block.break_even_kes} soldSoFar={block.sales_today_kes} coveredAt={block.crossed_at} />
      {block.curve && block.curve.length > 0 && <div className="mt-3"><BreakEvenLine points={block.curve.map((p) => ({ at: p.at, sales: p.sales_kes }))} breakEven={block.break_even_kes} coveredAt={block.crossed_at} toGo={block.to_go_kes} /></div>}
      <p className="mt-3 text-xs">Your fixed costs come to <b>{kes(block.fixed_per_day_kes)} a day</b>. Built from {block.built_from.label}.</p>
      <details className="mt-1">
        <summary className="flex min-h-10 cursor-pointer items-center text-[11px] font-semibold text-[var(--v-muted-foreground)]">What is in it</summary>
        <ul className="mt-1 space-y-0.5 text-[11px] text-[var(--v-muted-foreground)]">{block.built_from.lines.map((l) => <li key={l.name} className="flex justify-between"><span>{l.name}</span><span className="tabular-nums">{kes(l.kes)}</span></li>)}</ul>
      </details>
      <Note>{block.note}</Note>
    </>)}</BlockFrame>
  );
}

function Bills({ block }: { block: BillsBlock }) {
  return (<>
    <BlockFrame title={T.bills} block={block}>{() => (<div className="grid gap-4 lg:grid-cols-[1.1fr_1fr]">
      <CashRunway label="Cash over the next 30 days" days={block.days.map((d) => ({ date: d.date, balance: d.balance_kes, bills: d.bills_kes }))} />
      <div>
      {block.shortfalls.length > 0
        ? <ul className="space-y-1">{block.shortfalls.slice(0, 3).map((s) => <li key={s.date} className="text-xs font-semibold text-[var(--v-destructive)]">You will be {kes(s.short_by_kes)} short on {shortDay(s.date)}, when {s.bills.join(" and ")} falls due.</li>)}</ul>
        : <p className="mt-3 text-xs font-semibold text-[var(--v-good)]">Your sales cover every bill in the next 30 days.</p>}
      {block.upcoming.length > 0 && (
        <ul className="mt-3 divide-y divide-[var(--v-border)] text-xs">
          {block.upcoming.map((u) => (
            <li key={`${u.id ?? u.name}-${u.due_on}`} className="flex items-center justify-between gap-3 py-1.5">
              <span>{u.name} · {u.days_away === 0 ? "today" : `in ${plural(u.days_away, "day")}`} ({shortDay(u.due_on)})</span>
              <span className="flex items-center gap-2">
                <b className="tabular-nums">{kes(u.amount_kes)}{u.short && <span className="ml-1.5"><Pill tone="bad">short</Pill></span>}</b>
                {u.id != null && <PayBill id={u.id} name={u.name} />}
              </span>
            </li>
          ))}
        </ul>
      )}
      {block.notes?.map((n) => <Note key={n}>{n}</Note>)}
      </div>
    </div>)}</BlockFrame>
    <BillForm />
  </>);
}

function PayBill({ id, name }: { id: number; name: string }) {
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState("");
  const [error, setError] = useState("");
  const pay = async () => {
    setBusy(true); setError(""); setSaved("");
    try {
      await api.post(`/api/v1/owner/money/bills/${id}/pay`, { method: "cash" });
      setSaved(`${name} is marked paid.`);
      window.dispatchEvent(new Event(OWNER_DATA_CHANGED));
    } catch {
      setError("Could not mark that bill paid.");
    } finally { setBusy(false); }
  };
  return (
    <span>
      <button type="button" disabled={busy} onClick={pay} className="min-h-10 text-[11px] font-bold text-[var(--v-primary)]">{busy ? "Saving…" : "Mark paid"}</button>
      {saved && <span role="status" className="ml-1 text-[11px] text-[var(--v-good)]">{saved}</span>}
      {error && <span role="alert" className="ml-1 text-[11px] text-[var(--v-warn)]">{error}</span>}
    </span>
  );
}

const field = "mt-1 block min-h-11 w-full rounded-lg border border-[var(--v-border)] bg-[var(--v-card)] px-3 text-sm";

function BillForm() {
  const [open, setOpen] = useState(false);
  const [categories, setCategories] = useState<{ key: string; name: string; id: number }[]>([]);
  const [name, setName] = useState("Rent");
  const [category, setCategory] = useState("premises");
  const [amount, setAmount] = useState("");
  const [frequency, setFrequency] = useState("monthly");
  const [dueDay, setDueDay] = useState("1");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  const load = () => {
    setOpen(true);
    api.get("/api/v1/owner/money/categories").then((r) => setCategories(r.data.categories ?? [])).catch(() => setError("Could not load cost lines."));
  };
  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(""); setSaved("");
    try {
      await api.post("/api/v1/owner/money/bills", { name, category, amount_kes: Number(amount), frequency, due_day: Number(dueDay) });
      setSaved(`${name} will show under bills and on Coming up.`);
      setAmount("");
      window.dispatchEvent(new Event(OWNER_DATA_CHANGED));
    } catch {
      setError("Could not save that bill. Check the amount and the day it falls due.");
    } finally { setBusy(false); }
  };
  const rename = async (id: number, next: string) => {
    await api.patch(`/api/v1/owner/money/categories/${id}`, { name: next });
    setCategories((rows) => rows.map((c) => c.id === id ? { ...c, name: next } : c));
  };
  if (!open) return <button type="button" onClick={load} className="min-h-10 text-[11px] font-bold text-[var(--v-primary)]">Add rent or a recurring bill</button>;
  return (
    <form onSubmit={save} className="space-y-3 rounded-lg border border-[var(--v-border)] bg-[var(--v-bg)] p-3.5">
      <h4 className="text-[11px] font-bold uppercase tracking-[0.12em] text-[var(--v-muted-foreground)]">Add a recurring bill</h4>
      <label className="block text-xs">Name<input className={field} value={name} onChange={(e) => setName(e.target.value)} required /></label>
      <label className="block text-xs">Cost line
        <select className={field} value={category} onChange={(e) => setCategory(e.target.value)}>
          {categories.length === 0 && <option value="premises">Rent & premises</option>}
          {categories.map((c) => <option key={c.key} value={c.key}>{c.name}</option>)}
        </select>
      </label>
      <div className="grid gap-3 sm:grid-cols-3">
        <label className="text-xs">Amount (KES)<input className={field} inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} required /></label>
        <label className="text-xs">How often
          <select className={field} value={frequency} onChange={(e) => setFrequency(e.target.value)}>
            <option value="weekly">Every week</option>
            <option value="monthly">Every month</option>
            <option value="yearly">Every year</option>
          </select>
        </label>
        <label className="text-xs">Due day<input className={field} inputMode="numeric" value={dueDay} onChange={(e) => setDueDay(e.target.value)} required /></label>
      </div>
      <button disabled={busy} className="min-h-10 rounded-lg bg-[var(--v-primary)] px-3 text-[11px] font-bold text-[var(--v-primary-foreground)]">{busy ? "Saving…" : "Save bill"}</button>
      {saved && <p role="status" className="text-xs text-[var(--v-good)]">{saved}</p>}
      {error && <p role="alert" className="text-xs text-[var(--v-warn)]">{error}</p>}
      {categories.length > 0 && (
        <details>
          <summary className="cursor-pointer text-[11px] font-semibold">Rename a cost line</summary>
          <ul className="mt-2 space-y-1">{categories.filter((c) => !c.key || true).slice(0, 8).map((c) => (
            <li key={c.id}><button type="button" className="text-[11px] font-semibold text-[var(--v-primary)]" onClick={() => { const next = window.prompt("Name for this cost line", c.name); if (next && next !== c.name) void rename(c.id, next); }}>Rename {c.name}</button></li>
          ))}</ul>
        </details>
      )}
    </form>
  );
}

function Spikes({ block }: { block: SpikesBlock }) {
  return (
    <BlockFrame title={T.spikes} block={block}>{() => (<>
      {block.spikes.length === 0 ? <Empty>No cost is running well above its usual.</Empty> : (
        <ul className="space-y-2.5">
          {block.spikes.map((s) => (
            <li key={s.name} className="text-xs">
              <div className="flex justify-between gap-3"><b>{s.name}</b><Pill tone="warn">up {s.up_pct}%</Pill></div>
              <p className="text-[var(--v-muted-foreground)]">{kes(s.this_month_kes)} this month against a usual {kes(s.usual_kes)} — {kes(s.extra_kes)} more.</p>
            </li>
          ))}
        </ul>
      )}
    </>)}</BlockFrame>
  );
}

function Savings({ block }: { block: SavingsBlock }) {
  return (
    <BlockFrame title={T.savings} block={block}>{() => (<>
      <Grid cols={3}>
        <Stat label="Kept this month" value={kes(block.captured_kes_month)} />
        <Stat label="Hours saved" value={`${block.hours_saved_30d}`} note="last 30 days" />
        <Stat label="Ideas you took" value={`${block.approved_ideas}`} />
      </Grid>
    </>)}</BlockFrame>
  );
}
