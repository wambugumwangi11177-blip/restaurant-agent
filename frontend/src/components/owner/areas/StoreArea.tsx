"use client";
import Link from "next/link";
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
      <Note>Recorded waste and internal transfers are excluded from this unexplained-usage comparison. Review physical counts and recipes before drawing conclusions.</Note>
      {flagged.length === 0
        ? <p className="text-xs font-semibold text-[var(--v-good)]">Nothing was used beyond what your sales explain in the last {block.window_days} days.</p>
        : (
          <ul className="space-y-3">
            {flagged.slice(0,5).map((i) => (
              <li key={i.item} className="text-xs">
                <div className="flex flex-wrap items-center justify-between gap-2"><b>{i.item}</b><Pill tone="bad">{i.off_by_pct}% off</Pill></div>
                <p className="mt-0.5">Used {num(i.used)} {i.unit}; your sales explain {num(i.expected)} {i.unit}. {i.missing > 0 ? <>That is <b>{num(i.missing)} {i.unit}</b> more, worth {kes(i.missing_value)}.</> : <>That is less than your sales explain: check the count.</>}</p>
              </li>
            ))}
          </ul>
        )}
      {rest.length > 0 && (
        <details className="mt-3">
          <summary className="flex min-h-10 cursor-pointer items-center text-[11px] font-semibold text-[var(--v-muted-foreground)]">The other items</summary>
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
      <div className="mb-4 grid grid-cols-3 items-center gap-2 rounded-xl bg-white p-4 text-center text-xs"><div><b>Store</b><p className="mt-1 text-[var(--v-muted-foreground)]">Records what was sent</p></div><div className="text-[var(--v-primary)]">Handover →<p className="mt-1">Both sides record</p></div><div><b>Kitchen</b><p className="mt-1 text-[var(--v-muted-foreground)]">Confirms what arrived</p></div></div>
      {!!block.pending&&<p className="mb-3 text-xs font-semibold text-[var(--v-warn)]">{block.pending} handovers still waiting for a declaration or confirmation.</p>}
      {!!block.transfers?.length&&<div className="mb-4 overflow-x-auto"><table className="w-full text-left text-xs"><thead><tr>{['Item','Store sent','Kitchen received','Status'].map(t=><th key={t} className="p-2">{t}</th>)}</tr></thead><tbody>{block.transfers.filter(t=>t.status!=="confirmed").slice(0,5).map(t=><tr key={t.id} className="border-t border-[var(--v-border)]"><th className="p-2">{t.item}</th><td className="p-2">{t.sent==null?'Not sent':`${num(t.sent)} ${t.unit}`}</td><td className="p-2">{t.received==null?'Not confirmed':`${num(t.received)} ${t.unit}`}</td><td className="p-2">{t.status}</td></tr>)}</tbody></table></div>}
      <Note>A handover mismatch is evidence at the door. Later missing stock cannot be assigned to a person or zone without independent physical counts and waste records.</Note>
      <Link href="/inventory" className="inline-flex min-h-11 items-center text-xs font-semibold text-[var(--v-primary)]">Open stock, counts and handovers →</Link>

      {block.doesnt_match.length === 0 ? <Empty>No disputed handovers recorded in this view.</Empty> : (
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
      {!!block.drafts.length&&<ul className="mt-3 space-y-2">{block.drafts.map((d,i)=><li key={i} className="rounded-lg border border-[var(--v-border)] bg-white p-3 text-xs"><b>{d.item ?? "Purchase draft"}</b> · {d.order != null ? `${d.order} ${d.unit ?? ""}` : `${d.lines ?? 0} lines`} · {d.supplier}</li>)}</ul>}
      <Link href="/purchasing" className="mt-3 inline-flex min-h-11 items-center rounded-lg bg-[var(--v-primary)] px-4 text-xs font-semibold text-white">Review orders & par levels →</Link>
      <Note>{plural(block.tracked, "item")} watched.{block.drafts.length ? ` ${plural(block.drafts.length, "draft order")} waiting for you.` : ""}</Note>
    </>)}</BlockFrame>
  );
}

function Suppliers({ block }: { block: SuppliersBlock }) {
  return (
    <BlockFrame title={T.suppliers} block={block}>{() => (<>
      <HBars label="Deliveries that came on time" max={100} rows={block.suppliers.slice(0,5).map((s) => ({ key: s.name, label: s.name, value: s.on_time_pct ?? 0, valueLabel: s.on_time_pct == null ? "Not enough deliveries yet" : `${s.on_time_pct}% · ${s.word}`, note: s.on_time_pct == null ? undefined : `${plural(s.closed_orders, "order")} closed`, flag: s.on_time_pct != null && s.on_time_pct < 80 }))} />
      {block.overdue_orders > 0 && <p className="mt-3 text-xs font-semibold text-[var(--v-destructive)]">{plural(block.overdue_orders, "order")} past the day it was due.</p>}
      {block.short_deliveries.length > 0 && (
        <ul className="mt-3 space-y-1 text-xs">
          {block.short_deliveries.map((d) => <li key={`${d.supplier}-${d.on}`}><b>{d.supplier}</b> delivered {num(d.received)} of {num(d.ordered)} {d.unit} of {d.item} on {shortDay(d.on)} — {num(d.short_by)} {d.unit} short, about {kes(d.short_value)}.</li>)}
        </ul>
      )}
    </>)}</BlockFrame>
  );
}
