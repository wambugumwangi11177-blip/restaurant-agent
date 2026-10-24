"use client";
import { useState } from "react";
import CustodyZones from "@/components/charts/CustodyZones";
import HBars from "@/components/charts/HBars";
import MissingFormula from "@/components/charts/MissingFormula";
import StockFlow from "@/components/charts/StockFlow";
import StockHistory from "@/components/charts/StockHistory";
import StockLevel from "@/components/charts/StockLevel";
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
  const [picked, setPicked] = useState<string | null>(null);
  return (
    <BlockFrame title={T.missing} block={block}>{() => { const flagged = block.items.filter((i) => i.check); const rest = block.items.filter((i) => !i.check).slice(0, 5); const shown = block.items.find((i) => i.item === picked) ?? flagged[0] ?? null; return (<>
      <StockFlow leaks={flagged.length} />
      <div className="mt-3"><MissingFormula item={shown ? { item: shown.item, unit: shown.unit, expected: shown.expected, used: shown.used, missing: shown.missing, missingValue: shown.missing_value } : null} /></div>
      {flagged.length === 0
        ? <p className="text-xs font-semibold text-[var(--v-good)]">Nothing was used beyond what your sales explain in the last {block.window_days} days.</p>
        : (
          <ul className="space-y-3">
            {flagged.map((i) => (
              <li key={i.item} className="text-xs">
                <div className="flex flex-wrap items-center justify-between gap-2"><button type="button" className="font-bold underline-offset-2 hover:underline" onClick={() => setPicked(i.item)}>{i.item}</button><Pill tone="bad">{i.off_by_pct}% off, last {block.window_days} days</Pill></div>
                <p className="mt-0.5">Used {num(i.used)} {i.unit}; your sales explain {num(i.expected)} {i.unit}. {i.missing > 0 ? <>That is <b>{num(i.missing)} {i.unit}</b> more, worth {kes(i.missing_value)}.</> : <>That is less than your sales explain: check the count.</>}</p>
              </li>
            ))}
          </ul>
        )}
      {rest.length > 0 && (
        <details className="mt-3">
          <summary className="flex min-h-10 cursor-pointer items-center text-[11px] font-semibold text-[var(--v-muted-foreground)]">The other items</summary>
          <div className="mt-2"><HBars label={`Used against what sales explain, last ${block.window_days} days`} max={100} rows={rest.map((i) => ({ key: i.item, label: i.item, value: Math.min(i.off_by_pct, 100), valueLabel: `${i.off_by_pct}% off`, note: `used ${num(i.used)} ${i.unit} · expected ${num(i.expected)} ${i.unit}` }))} /></div>
        </details>
      )}
      <Note>Last {block.window_days} days. A reason to check the store and the portions, not a finding about anyone.</Note>
    </>); }}</BlockFrame>
  );
}

function Handover({ block }: { block: HandoverBlock }) {
  return (
    <BlockFrame title={T.handover} block={block}>{() => (<>
      <CustodyZones gaps={block.doesnt_match.map((h) => ({ item: h.item, unit: h.unit, store: h.store_said, kitchen: h.kitchen_counted }))} />
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
      {block.history && <StockHistory item={block.history.item} unit={block.history.unit} points={block.history.points} reorder={block.history.reorder} par={block.history.par} state={block.history.state} reason={block.history.reason} windowLabel={block.history.window || "last 14 days"} />}
      {block.time_to_reorder.length > 0 && (
        <ul className="mb-3 space-y-2 text-xs">{block.time_to_reorder.map((r) => <li key={r.item}><Pill tone="warn">Time to reorder</Pill> <b className="ml-1">{r.item}</b> · {num(r.left)} {r.unit} left<StockLevel item={r.item} unit={r.unit} left={r.left} reorder={r.reorder_point ?? null} par={r.par ?? null} /></li>)}</ul>
      )}
      {block.time_to_reorder.length === 0 && block.least_cover[0] && (
        <StockLevel item={block.least_cover[0].item} unit={block.least_cover[0].unit} left={block.least_cover[0].left} reorder={block.least_cover[0].reorder_point ?? null} par={block.least_cover[0].par ?? null} />
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
