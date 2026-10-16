"use client";
import HBars from "@/components/charts/HBars";
import { BLOCK_TITLES } from "@/lib/owner/blocks";
import { kes, plural, shortDay } from "@/lib/owner/format";
import type { HandoverBlock, MissingBlock, ReorderBlock, SuppliersBlock } from "@/lib/owner/areaTypes";
import type { Area } from "@/lib/owner/types";
import { BlockFrame, Empty, Note, Pill } from "./ui";

const T = BLOCK_TITLES.store;
const num = (n: number) => String(Number(n.toFixed(2)));

export default function StoreArea({ area }: { area: Area }) {
  const b = area.blocks;
  return (
    <div className="space-y-3">
      <Missing block={b.missing as MissingBlock} />
      <div className="grid gap-3 md:grid-cols-2">
        <Handover block={b.handover as HandoverBlock} />
        <Reorder block={b.reorder as ReorderBlock} />
      </div>
      <Suppliers block={b.suppliers as SuppliersBlock} />
    </div>
  );
}

function Missing({ block }: { block: MissingBlock }) {
  return (
    <BlockFrame title={T.missing} block={block}>{() => { const flagged = block.items.filter((i) => i.check); const rest = block.items.filter((i) => !i.check).slice(0, 5); return (<>
      {flagged.length === 0
        ? <p className="text-xs font-semibold text-[var(--v-good)]">Nothing was used beyond what your sales explain in the last {block.window_days} days.</p>
        : (
          <ul className="space-y-3">
            {flagged.map((i) => (
              <li key={i.item} className="text-xs">
                <div className="flex flex-wrap items-center justify-between gap-2"><b>{i.item}</b><Pill tone="bad">{i.off_by_pct}% off</Pill></div>
                <p className="mt-0.5">Used {num(i.used)} {i.unit}; your sales explain {num(i.expected)} {i.unit}. {i.missing > 0 ? <>That is <b>{num(i.missing)} {i.unit}</b> more, worth {kes(i.missing_value)}.</> : <>That is less than your sales explain: check the count.</>}</p>
              </li>
            ))}
          </ul>
        )}
      {rest.length > 0 && (
        <details className="mt-3">
          <summary className="cursor-pointer text-[11px] font-semibold text-[var(--v-muted-foreground)]">The other items</summary>
          <div className="mt-2"><HBars label="Used against what sales explain" max={100} rows={rest.map((i) => ({ key: i.item, label: i.item, value: Math.min(i.off_by_pct, 100), valueLabel: `${i.off_by_pct}% off`, note: `used ${num(i.used)} ${i.unit} · expected ${num(i.expected)} ${i.unit}` }))} /></div>
        </details>
      )}
      <Note>Last {block.window_days} days. A reason to check the store and the portions, not a finding about anyone.</Note>
    </>); }}</BlockFrame>
  );
}

function Handover({ block }: { block: HandoverBlock }) {
  return (
    <BlockFrame title={T.handover} block={block}>{() => (<>
      {block.doesnt_match.length === 0 ? <Empty>Every handover from the store matched what the kitchen counted.</Empty> : (
        <ul className="space-y-2 text-xs">
          {block.doesnt_match.map((h) => <li key={h.item}><b>{h.item}</b>: the store said {num(h.store_said)} {h.unit}, the kitchen counted {num(h.kitchen_counted)} {h.unit} — <b>{num(Math.abs(h.gap))} {h.unit}</b> apart.</li>)}
        </ul>
      )}
    </>)}</BlockFrame>
  );
}

function Reorder({ block }: { block: ReorderBlock }) {
  return (
    <BlockFrame title={T.reorder} block={block}>{() => (<>
      {block.time_to_reorder.length > 0 && (
        <ul className="mb-3 space-y-1 text-xs">{block.time_to_reorder.map((r) => <li key={r.item}><Pill tone="warn">Time to reorder</Pill> <b className="ml-1">{r.item}</b> · {num(r.left)} {r.unit} left</li>)}</ul>
      )}
      {block.least_cover.length > 0
        ? <HBars label="Days of cover left" rows={block.least_cover.filter((r) => r.days_left != null).map((r) => ({ key: r.item, label: r.item, value: r.days_left as number, valueLabel: `${num(r.days_left as number)} days`, note: `${num(r.left)} ${r.unit} on the shelf` }))} />
        : <Empty>Everything has plenty of cover.</Empty>}
      <Note>{plural(block.tracked, "item")} watched.{block.drafts.length ? ` ${plural(block.drafts.length, "draft order")} waiting for you.` : ""}</Note>
    </>)}</BlockFrame>
  );
}

function Suppliers({ block }: { block: SuppliersBlock }) {
  return (
    <BlockFrame title={T.suppliers} block={block}>{() => (<>
      <HBars label="Deliveries that came on time" max={100} rows={block.suppliers.map((s) => ({ key: s.name, label: s.name, value: s.on_time_pct ?? 0, valueLabel: s.on_time_pct == null ? "Not enough deliveries yet" : `${s.on_time_pct}% · ${s.word}`, note: s.on_time_pct == null ? undefined : `${plural(s.closed_orders, "order")} closed`, flag: s.on_time_pct != null && s.on_time_pct < 80 }))} />
      {block.overdue_orders > 0 && <p className="mt-3 text-xs font-semibold text-[var(--v-destructive)]">{plural(block.overdue_orders, "order")} past the day it was due.</p>}
      {block.short_deliveries.length > 0 && (
        <ul className="mt-3 space-y-1 text-xs">
          {block.short_deliveries.map((d) => <li key={`${d.supplier}-${d.on}`}><b>{d.supplier}</b> delivered {num(d.received)} of {num(d.ordered)} {d.unit} of {d.item} on {shortDay(d.on)} — {num(d.short_by)} {d.unit} short, about {kes(d.short_value)}.</li>)}
        </ul>
      )}
    </>)}</BlockFrame>
  );
}
