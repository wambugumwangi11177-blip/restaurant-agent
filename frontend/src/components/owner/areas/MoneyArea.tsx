"use client";
import Link from "next/link";
import PriceImpact from "@/components/owner/PriceImpact";
import { useContext, useState } from "react";
import { Download } from "lucide-react";
import api from "@/lib/api";
import CashRunway from "@/components/charts/CashRunway";
import BreakEvenClock from "@/components/charts/BreakEvenClock";
import Dial from "@/components/charts/Dial";
import StackedBar from "@/components/charts/StackedBar";
import Waterfall, { type Step } from "@/components/charts/Waterfall";
import { BLOCK_TITLES } from "@/lib/owner/blocks";
import { kes, plural, shortDay } from "@/lib/owner/format";
import type { BillsBlock, BreakEvenBlock, CostDialsBlock, PnlBlock, SavingsBlock, SpikesBlock } from "@/lib/owner/areaTypes";
import type { Area } from "@/lib/owner/types";
import { AreaFocus, BlockFrame, Empty, Grid, Note, Pill, Stat } from "./ui";

const T = BLOCK_TITLES.money;
const tone = (word: string) => (word === "Fine" ? "good" : word === "Watch" ? "warn" : "bad") as "good" | "warn" | "bad";

export default function MoneyArea({ area }: { area: Area }) {
  const b = area.blocks;
  const focus = useContext(AreaFocus);
  return (
    <div className="space-y-3">
      {['food-cost','wages','prime-cost'].includes(focus)&&<CostMeasure block={b.cost_dials as CostDialsBlock} kind={focus}/>}
      <Pnl block={b.pnl as PnlBlock} />
      {(!focus || focus === "price-impact") && <PriceImpact />}
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
        {block.prime_cost_pct != null && <Dial value={block.prime_cost_pct} target={block.prime_cost_target_pct ?? 62} label="Ingredients + wages (prime cost)" word={block.prime_cost_word ?? "Learning"} tone={tone(block.prime_cost_word ?? "Watch")} />}
        <Dial value={block.wages_pct} target={block.wages_target_pct} label="Out of every KES 100, wages" word={block.wages_word} tone={tone(block.wages_word)} />
      </div>
    </>)}</BlockFrame>
  );
}

function Clock({ block }: { block: BreakEvenBlock }) {
  return (
    <BlockFrame title={T.breakeven} block={block}>{() => (<>
      <p className="mb-4 text-sm">Break-even: the sales needed today to cover your recorded fixed costs after ingredients.</p>
      <BreakEvenClock label="Costs covered" breakEven={block.break_even_kes} soldSoFar={block.sales_today_kes} coveredAt={block.crossed_at} />
      <p className="mt-3 text-xs">Your fixed costs come to <b>{kes(block.fixed_per_day_kes)} a day</b>. Built from {block.built_from.label}.</p>
      <div className="my-4 grid gap-3 sm:grid-cols-3"><Stat label="Daily sales target" value={kes(block.break_even_kes)}/><Stat label="Sold today" value={kes(block.sales_today_kes)}/><Stat label="Still to sell" value={kes(block.to_go_kes)}/></div>
      <p className="text-xs">Daily fixed costs ÷ the share left after ingredients = daily sales target. Ingredient share: {block.food_cost_pct}% from {block.built_from.label}.</p>
      {block.sales_today_kes===0&&<Note>No paid sales recorded today. The target is still shown; the ring will fill as sales arrive.</Note>}
      <details open className="mt-1">
        <summary className="flex min-h-10 cursor-pointer items-center text-[11px] font-semibold text-[var(--v-muted-foreground)]">What is in it</summary>
        <ul className="mt-1 space-y-0.5 text-[11px] text-[var(--v-muted-foreground)]">{block.built_from.lines.map((l) => <li key={l.name} className="flex justify-between"><span>{l.name}</span><span className="tabular-nums">{kes(l.kes)}</span></li>)}</ul>
        {block.built_from.wages_kes>0&&<p className="mt-2 text-xs">Fixed wages included: {kes(block.built_from.wages_kes)}</p>}
        <Link href="/entries" className="mt-2 inline-flex min-h-10 items-center text-xs underline">Review costs in team entries →</Link>
      </details>
      <Note>{block.note}</Note>
    </>)}</BlockFrame>
  );
}

function Bills({ block }: { block: BillsBlock }) {
  return (
    <BlockFrame title={T.bills} block={block}>{() => (<div className="grid gap-4 lg:grid-cols-[1.1fr_1fr]">
      <CashRunway label="Cash over the next 30 days" days={block.days.map((d) => ({ date: d.date, balance: d.balance_kes, bills: d.bills_kes }))} />
      <div>
      {block.shortfalls.length > 0
        ? <ul className="space-y-1">{block.shortfalls.slice(0, 3).map((s) => <li key={s.date} className="text-xs font-semibold text-[var(--v-destructive)]">You will be {kes(s.short_by_kes)} short on {shortDay(s.date)}, when {s.bills.join(" and ")} falls due.</li>)}</ul>
        : <p className="mt-3 text-xs font-semibold text-[var(--v-good)]">Your sales cover every bill in the next 30 days.</p>}
      {block.upcoming.length > 0 && (
        <ul className="mt-3 divide-y divide-[var(--v-border)] text-xs">
          {block.upcoming.map((u) => (
            <li key={`${u.name}-${u.due_on}`} className="flex items-center justify-between gap-3 py-1.5">
              <span>{u.name} · {u.days_away === 0 ? "today" : `in ${plural(u.days_away, "day")}`} ({shortDay(u.due_on)})</span>
              <b className="tabular-nums">{kes(u.amount_kes)}{u.short && <span className="ml-1.5"><Pill tone="bad">short</Pill></span>}</b>
            </li>
          ))}
        </ul>
      )}
      {block.notes?.map((n) => <Note key={n}>{n}</Note>)}
      </div>
    </div>)}</BlockFrame>
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

function CostMeasure({block,kind}:{block:CostDialsBlock;kind:string}) {
 const data=block as CostDialsBlock & {period?:{label:string;from?:string;to?:string};sales_kes?:number;ingredients_kes?:number;wages_kes?:number;notes?:string[]};
 const title=kind==='food-cost'?'Food cost':kind==='wages'?'Wages':'Prime cost';
 const value=kind==='food-cost'?block.food_cost_pct:kind==='wages'?block.wages_pct:block.prime_cost_pct;
 const target=kind==='food-cost'?block.food_cost_target_pct:kind==='wages'?block.wages_target_pct:block.prime_cost_target_pct;
 const amount=kind==='food-cost'?data.ingredients_kes:kind==='wages'?data.wages_kes:data.ingredients_kes!=null&&data.wages_kes!=null?data.ingredients_kes+data.wages_kes:null;
 const rule=kind==='food-cost'?'food_cost_target_pct':kind==='wages'?'labour_target_pct':'prime_cost_target_pct';
 const rules=block.assumptions?.filter(a=>a.setting===rule)??[];
 const notes=data.notes?.filter(note=>kind==='prime-cost'||(kind==='food-cost'?!/wages|payroll|meals/i.test(note):!/ingredient cost/i.test(note)));
 return <BlockFrame title={title} block={{...block,assumptions:rules,assumption:rules[0]}}>{()=><div className="space-y-4"><p className="text-sm">{data.period?.label??'Last 30 calendar days'}{data.period?.from&&` (${data.period.from} to ${data.period.to})`} · the same sales denominator across food, wages and prime cost.</p><div className="grid gap-4 sm:grid-cols-3"><Stat label={title+' share'} value={value==null?'Not recorded':`${value.toFixed(1)}%`}/><Stat label="Recorded cost" value={kes(amount)}/><Stat label="Your target" value={target==null?'Not set':`${target}%`}/></div><p className="text-sm">{kind==='food-cost'?'Ingredients used by your recorded sales. This is different from money spent buying stock.':kind==='wages'?'Recorded payroll or shift-based wages against sales. Any estimates remain labelled in Profit & Loss.':'Ingredients plus wages. The combined result is useful for control, while the two costs remain separately reviewable.'}</p>{notes?.map(note=><Note key={note}>{note}</Note>)}<Link href={kind==='food-cost'?'/planning?tool=recipe-plan':kind==='wages'?'/areas/staff?tool=wages':'/areas/money?tool=profit-and-loss'} className="leviii-primary-button">{kind==='food-cost'?'Review recipes & yield':kind==='wages'?'Review wages & shifts':'Open Profit & Loss'} →</Link></div>}</BlockFrame>;
}
