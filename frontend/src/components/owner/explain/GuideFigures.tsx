import ChartEmpty from "@/components/charts/ChartEmpty";
import ShortCount from "@/components/charts/ShortCount";
import StockHistory from "@/components/charts/StockHistory";
import ThreeWayMatch from "@/components/charts/ThreeWayMatch";
import { kes } from "@/lib/owner/format";
import type { BlockState } from "@/lib/owner/types";

type Fig = { state?: BlockState; reason?: string | null; window?: string; day?: number; of?: number } & Record<string, unknown>;

function Empty({ fig, fallback }: { fig?: Fig; fallback: string }) {
  return <ChartEmpty state={fig?.state ?? "no_data"} reason={(fig?.reason as string) || fallback} day={fig?.day} of={fig?.of} />;
}

function hasRows(fig: Fig | undefined, key: string): boolean {
  const rows = fig?.[key];
  return Array.isArray(rows) && rows.length > 0 && fig?.state !== "no_data" && fig?.state !== "unavailable";
}

/** The guide pictures that need their own series. Each one says when it has nothing to draw. */
export default function GuideFigures({ figures }: { figures?: Record<string, Fig> }) {
  const f = figures ?? {};
  const three = f.three_way;
  const legs = ((three?.legs as { key: string; label: string; left_kes: number | null; right_kes: number | null; left_label?: string; right_label?: string; look: boolean }[]) || []).map((leg) => ({
    key: leg.key,
    label: leg.label,
    left: leg.left_kes == null ? (leg.left_label || "Not recorded") : kes(leg.left_kes),
    right: leg.right_kes == null ? (leg.right_label || "Not recorded") : kes(leg.right_kes),
    gap: leg.left_kes != null && leg.right_kes != null ? kes(Math.abs(leg.left_kes - leg.right_kes)) : "not recorded",
    look: Boolean(leg.look),
  }));
  const ladder = (f.price_ladder?.rungs as { dish: string; price_kes: number }[]) || [];
  const pareto = (f.pareto?.points as { dish: string; sales_kes: number; cumulative_pct: number }[]) || [];
  const tree = (f.price_tree?.nodes as { title: string; detail: string }[]) || [];
  const slope = (f.elasticity?.points as { price_kes: number | null; portions: number | null }[]) || [];
  const abc = (f.abc_calendar?.cells as { item: string; abc: string; days: string[] }[]) || [];
  const why = (f.why_tree?.drivers as { key: string; label: string; found: boolean; detail: string }[]) || [];
  const pyramid = (f.alert_pyramid?.levels as { key: string; label: string; count: number }[]) || [];
  const doors = (f.door_cards?.doors as { key: string; title: string; window: string; signal: string; detail: string }[]) || [];
  const shilling = (f.shilling?.steps as { step: string; detail: string }[]) || [];
  const maxPrice = Math.max(...ladder.map((r) => r.price_kes), 1);

  return (
    <div className="space-y-4">
      <section aria-label="Three-way match">
        <h3 className="text-sm font-semibold">Three-way match</h3>
        {legs.length ? <ThreeWayMatch legs={legs} label={`Three-way match, ${String(three?.window || "latest cash count")}`} /> : <Empty fig={three} fallback="A cash count, an M-Pesa statement and card sales will meet here for each shift." />}
      </section>
      <section aria-label="Short count">
        <h3 className="text-sm font-semibold">The trick a short count catches</h3>
        {f.short_count?.bars ? (
          <ShortCount expected={Number(f.short_count.expected_kes)} counted={Number(f.short_count.counted_kes)} gap={Number(f.short_count.gap_kes)} trick={f.short_count.trick as string | null} windowLabel={String(f.short_count.window || "last 14 days")} state={f.short_count.state} reason={f.short_count.reason as string} />
        ) : <Empty fig={f.short_count} fallback="A short count draws here once a drawer is counted." />}
      </section>
      <section aria-label="Stock history">
        <h3 className="text-sm font-semibold">Stock against the reorder line</h3>
        <StockHistory item={f.stock_history?.item as string} unit={f.stock_history?.unit as string} points={f.stock_history?.points as { date: string; on_hand: number }[]} reorder={f.stock_history?.reorder as number | null} par={f.stock_history?.par as number | null} state={f.stock_history?.state} reason={f.stock_history?.reason as string} windowLabel={String(f.stock_history?.window || "last 14 days")} />
      </section>
      <section aria-label="Follow a shilling">
        <h3 className="text-sm font-semibold">Follow a shilling</h3>
        {hasRows(f.shilling, "steps") ? (
          <ol className="space-y-1 text-xs" aria-label="One order through the statement">
            {shilling.map((s) => <li key={s.step}><b>{s.step}.</b> {s.detail}</li>)}
          </ol>
        ) : <Empty fig={f.shilling} fallback="Follow a shilling once a paid order is recorded." />}
      </section>
      <section aria-label="Price decision">
        <h3 className="text-sm font-semibold">How a price is decided</h3>
        {hasRows(f.price_tree, "nodes") ? (
          <ol className="space-y-1 text-xs">{tree.map((n, i) => <li key={n.title}><b>{i + 1}. {n.title}.</b> {n.detail}</li>)}</ol>
        ) : <Empty fig={f.price_tree} fallback="A price decision needs a dish with a cost and a menu price." />}
      </section>
      <section aria-label="Elasticity">
        <h3 className="text-sm font-semibold">How portions moved when the price moved</h3>
        {hasRows(f.elasticity, "points") ? (
          <svg role="img" aria-label="Elasticity slope" viewBox="0 0 320 80" className="w-full">
            {slope.length >= 2 && slope[0].price_kes != null && slope[1].price_kes != null && (
              <line x1="40" y1={slope[0].portions == null ? 40 : 60} x2="260" y2={slope[1].portions == null ? 40 : 20} stroke="var(--v-primary)" strokeWidth="2" />
            )}
            <text x="16" y="74" fontSize="8" fill="var(--v-muted-foreground)">{slope.map((p) => `${kes(p.price_kes ?? 0)}${p.portions == null ? "" : ` · ${p.portions}`}`).join("  →  ")}</text>
          </svg>
        ) : <Empty fig={f.elasticity} fallback="Approve a price change to see how portions moved." />}
      </section>
      <section aria-label="Price ladder">
        <h3 className="text-sm font-semibold">Price ladder</h3>
        {hasRows(f.price_ladder, "rungs") ? (
          <ul className="space-y-1" aria-label="Menu prices, low to high">
            {ladder.map((r) => (
              <li key={r.dish} className="grid grid-cols-[7rem_1fr_4rem] items-center gap-2 text-[11px]">
                <span className="truncate">{r.dish}</span>
                <span className="h-2 rounded-full bg-[var(--v-primary)]" style={{ width: `${Math.max(8, (r.price_kes / maxPrice) * 100)}%` }} />
                <span className="text-right">{kes(r.price_kes)}</span>
              </li>
            ))}
          </ul>
        ) : <Empty fig={f.price_ladder} fallback="The price ladder fills in once dishes have a menu price." />}
      </section>
      <section aria-label="Pareto">
        <h3 className="text-sm font-semibold">Where sales add up</h3>
        {hasRows(f.pareto, "points") ? (
          <ol className="space-y-1 text-xs" aria-label={`Cumulative sales, ${String(f.pareto?.window || "last 30 days")}`}>
            {pareto.map((p) => <li key={p.dish} className="flex justify-between gap-3"><span>{p.dish}</span><span>{kes(p.sales_kes)} · {p.cumulative_pct}%</span></li>)}
          </ol>
        ) : <Empty fig={f.pareto} fallback="The cumulative line needs paid sales in the last 30 days." />}
      </section>
      <section aria-label="Count calendar">
        <h3 className="text-sm font-semibold">What to count</h3>
        {hasRows(f.abc_calendar, "cells") ? (
          <ul className="space-y-1 text-xs" aria-label="ABC count calendar, next 14 days">
            {abc.map((c) => <li key={c.item}><b>{c.abc}</b> · {c.item}{c.days.length ? ` · ${c.days.join(", ")}` : " · no count in the next 14 days"}</li>)}
          </ul>
        ) : <Empty fig={f.abc_calendar} fallback="The count calendar fills in once stock items are recorded." />}
      </section>
      <section aria-label="Why tree">
        <h3 className="text-sm font-semibold">Why yesterday</h3>
        {hasRows(f.why_tree, "drivers") ? (
          <ul className="space-y-1 text-xs" aria-label={`Why tree, ${String(f.why_tree?.window || "yesterday")}`}>
            {why.map((d) => <li key={d.key}><b>{d.label}:</b> {d.found ? "Look here. " : "Not found. "}{d.detail}</li>)}
          </ul>
        ) : <Empty fig={f.why_tree} fallback="A why-tree needs a day of sales to explain." />}
      </section>
      <section aria-label="Alert pyramid">
        <h3 className="text-sm font-semibold">What reaches you</h3>
        {hasRows(f.alert_pyramid, "levels") ? (
          <ul className="space-y-1 text-xs" aria-label="Alerts, last 7 days">
            {pyramid.map((level) => <li key={level.key} className="flex justify-between"><span>{level.label}</span><b>{level.count}</b></li>)}
          </ul>
        ) : <Empty fig={f.alert_pyramid} fallback="No alerts in the last 7 days." />}
      </section>
      <section aria-label="Door cards">
        <h3 className="text-sm font-semibold">What can fail, and where</h3>
        {doors.length && f.door_cards?.state !== "no_data" ? (
          <ul className="grid gap-2 sm:grid-cols-2">
            {doors.map((d) => (
              <li key={d.key} className="rounded-lg border border-[var(--v-border)] p-3 text-xs">
                <p className="font-semibold">{d.title}</p>
                <p className="text-[10px] uppercase tracking-[0.12em] text-[var(--v-muted-foreground)]">{d.window}</p>
                <p className="mt-1">{d.detail}</p>
              </li>
            ))}
          </ul>
        ) : <Empty fig={f.door_cards} fallback="Each door fills in once that part of the restaurant has records." />}
      </section>
    </div>
  );
}
