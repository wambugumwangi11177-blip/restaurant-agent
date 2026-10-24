import ChartEmpty from "@/components/charts/ChartEmpty";
import ShortCount from "@/components/charts/ShortCount";
import StockHistory from "@/components/charts/StockHistory";
import ThreeWayMatch from "@/components/charts/ThreeWayMatch";
import { kes, shortDay, weekday } from "@/lib/owner/format";
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
        {f.short_count?.bars || f.short_count?.example ? (
          <ShortCount expected={Number(f.short_count.expected_kes)} counted={Number(f.short_count.counted_kes)} gap={Number(f.short_count.gap_kes)} trick={f.short_count.trick as string | null} windowLabel={String(f.short_count.window || "last 14 days")} state={f.short_count.state} reason={f.short_count.reason as string} example={Boolean(f.short_count.example)} />
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
          <ol className="space-y-1" aria-label="Price decision tree">
            {tree.map((n, i) => (
              <li key={n.title}>
                <div className="rounded-lg border border-[var(--v-border)] px-3 py-2 text-xs"><b>{n.title}.</b> {n.detail}</div>
                {i < tree.length - 1 && <div aria-hidden className="mx-auto h-3 w-px bg-[var(--chart-bar,#e0b15a)]" />}
              </li>
            ))}
          </ol>
        ) : <Empty fig={f.price_tree} fallback="A price decision needs a dish with a cost and a menu price." />}
      </section>
      <section aria-label="Elasticity">
        <h3 className="text-sm font-semibold">How portions moved when the price moved</h3>
        {hasRows(f.elasticity, "points") ? <Elasticity points={slope} /> : <Empty fig={f.elasticity} fallback="Approve a price change to see how portions moved." />}
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
        {hasRows(f.pareto, "points") ? <Pareto points={pareto} windowLabel={String(f.pareto?.window || "last 30 days")} /> : <Empty fig={f.pareto} fallback="The cumulative line needs paid sales in the last 30 days." />}
      </section>
      <section aria-label="Count calendar">
        <h3 className="text-sm font-semibold">What to count</h3>
        {hasRows(f.abc_calendar, "cells") ? <CountCalendar cells={abc} /> : <Empty fig={f.abc_calendar} fallback="The count calendar fills in once stock items are recorded." />}
      </section>
      <section aria-label="Why tree">
        <h3 className="text-sm font-semibold">Why yesterday</h3>
        {hasRows(f.why_tree, "drivers") ? (
          <div aria-label={`Why tree, ${String(f.why_tree?.window || "yesterday")}`} className="grid gap-2 sm:grid-cols-2">
            {why.map((d) => (
              <div key={d.key} className="rounded-lg border-l-4 bg-[var(--v-muted)] px-3 py-2 text-xs" style={{ borderColor: d.found ? "var(--chart-cost, #fbbf24)" : "var(--v-border)" }}>
                <b>{d.label}</b>
                <p className="mt-0.5">{d.found ? "Look here. " : "Not found. "}{d.detail}</p>
              </div>
            ))}
          </div>
        ) : <Empty fig={f.why_tree} fallback="A why-tree needs a day of sales to explain." />}
      </section>
      <section aria-label="Alert pyramid">
        <h3 className="text-sm font-semibold">What reaches you</h3>
        {hasRows(f.alert_pyramid, "levels") ? (
          <div aria-label="Alert pyramid, last 7 days" className="space-y-1">
            {pyramid.map((level, i) => (
              <div key={level.key} className="mx-auto flex h-9 items-center justify-center rounded-sm text-xs font-semibold text-[#0c0c0c]" style={{ width: `${100 - i * 16}%`, background: i === 0 ? "var(--danger, #f87171)" : i === 1 ? "var(--chart-cost, #fbbf24)" : "var(--chart-bar, #e0b15a)" }}>
                {level.label} · {level.count}
              </div>
            ))}
          </div>
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

function Elasticity({ points }: { points: { price_kes: number | null; portions: number | null }[] }) {
  const priced = points.filter((p) => p.price_kes != null);
  const maxPortions = Math.max(...points.map((p) => p.portions ?? 0), 1);
  const xs = priced.map((_, i) => 48 + (priced.length === 1 ? 0 : (i / (priced.length - 1)) * 240));
  const y = (portions: number | null) => 16 + (1 - (portions ?? 0) / maxPortions) * 70;
  const line = priced.map((p, i) => `${i === 0 ? "M" : "L"} ${xs[i]} ${y(p.portions)}`).join(" ");
  return (
    <svg role="img" aria-label="How portions moved when the price moved" viewBox="0 0 320 120" className="w-full">
      <line x1="40" y1="12" x2="40" y2="92" stroke="var(--v-muted-foreground)" />
      <line x1="40" y1="92" x2="300" y2="92" stroke="var(--v-muted-foreground)" />
      <text x="8" y="14" fontSize="8" fill="var(--v-muted-foreground)">Portions</text>
      <text x="250" y="108" fontSize="8" fill="var(--v-muted-foreground)">Price</text>
      {line && <path d={line} fill="none" stroke="var(--chart-bar, #e0b15a)" strokeWidth="2" />}
      {priced.map((p, i) => <text key={i} x={xs[i]} y="104" textAnchor="middle" fontSize="8" fill="var(--v-muted-foreground)">{kes(p.price_kes ?? 0)}</text>)}
    </svg>
  );
}

function Pareto({ points, windowLabel }: { points: { dish: string; sales_kes: number; cumulative_pct: number }[]; windowLabel: string }) {
  const max = Math.max(...points.map((p) => p.sales_kes), 1);
  const slot = 300 / points.length;
  const line = points.map((p, i) => `${i === 0 ? "M" : "L"} ${16 + slot * i + slot / 2} ${88 - (p.cumulative_pct / 100) * 70}`).join(" ");
  return (
    <figure>
      <svg role="img" aria-label={`Cumulative sales, ${windowLabel}`} viewBox="0 0 320 110" className="w-full">
        {points.map((p, i) => {
          const h = Math.max((p.sales_kes / max) * 70, 2);
          const x = 16 + slot * i + 4;
          return <rect key={p.dish} x={x} y={88 - h} width={Math.max(slot - 8, 4)} height={h} fill="var(--chart-bar, #e0b15a)"><title>{p.dish}: {kes(p.sales_kes)}</title></rect>;
        })}
        <path d={line} fill="none" stroke="var(--chart-line, #60a5fa)" strokeWidth="2" />
      </svg>
      <ul className="mt-1 space-y-0.5 text-[11px]">{points.slice(0, 6).map((p) => <li key={p.dish} className="flex justify-between gap-2"><span className="truncate">{p.dish}</span><span>{kes(p.sales_kes)} · {p.cumulative_pct}%</span></li>)}</ul>
    </figure>
  );
}

function CountCalendar({ cells }: { cells: { item: string; abc: string; days: string[] }[] }) {
  const days = [...new Set(cells.flatMap((c) => c.days))].sort().slice(0, 14);
  if (days.length === 0) return <p className="text-xs">No count is scheduled in the next 14 days.</p>;
  return (
    <div className="overflow-x-auto" aria-label="ABC count calendar">
      <table className="w-full border-collapse text-center text-[11px]">
        <thead>
          <tr>
            <th className="p-1 text-left">Item</th>
            {days.map((d) => <th key={d} className="p-1 font-medium">{weekday(d)}<br />{shortDay(d)}</th>)}
          </tr>
        </thead>
        <tbody>
          {cells.slice(0, 8).map((c) => (
            <tr key={c.item}>
              <th className="p-1 text-left font-medium">{c.abc} · {c.item}</th>
              {days.map((d) => <td key={d} className="p-1">{c.days.includes(d) ? "●" : "·"}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
