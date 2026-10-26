"use client";
import { useContext } from "react";
import Link from "next/link";
import { BLOCK_TITLES } from "@/lib/owner/blocks";
import { plural, shortDay } from "@/lib/owner/format";
import type { DataTrustBlock, InfoBlock, LicencesBlock, SettingsBlock } from "@/lib/owner/areaTypes";
import { useSettings } from "@/components/owner/settings/SettingsProvider";
import type { Area } from "@/lib/owner/types";
import { AreaFocus, BlockFrame, Empty, Note, Pill, Stat } from "./ui";

const T = BLOCK_TITLES.permits;
const LICENCE_TONE: Record<string, "good" | "warn" | "bad"> = { ok: "good", expiring: "warn", expired: "bad" };

export default function PermitsArea({ area }: { area: Area }) {
  const b = area.blocks;
  const focus = useContext(AreaFocus);
  return (
    <div className="space-y-3">
      {(!focus || focus==='source-readiness') && <section id="your-data" className="rounded-xl border border-[var(--v-border)] bg-white p-5"><p className="leviii-eyebrow">Your guide · pages 4–8</p><h2 className="text-xl font-semibold">Three doors. One set of records.</h2><div className="mt-4 grid gap-3 md:grid-cols-3">{[
        {name:"01 · Sales",detail:(b.till_connection as InfoBlock).source==="direct"?"Recorded directly in this workspace. A real till connection is configured for your restaurant during onboarding.":"Read automatically from the till. Connection and reconciliation status are shown below.",href:"/areas/sales_dishes?tool=sales-last-7-days",action:"See sales"},
        {name:"02 · Your team",detail:"Expenses, deliveries, invoices, physical counts, kitchen issues and staff pay. Profit depends on costs being entered.",href:"/entries",action:"Open team entries"},
        {name:"03 · M-Pesa statement",detail:"Upload the statement and check payments against sales. No uploaded statement means an incomplete check.",href:"/areas/cash?tool=m-pesa-check",action:"Check M-Pesa"},
      ].map(door=><article key={door.name} className="rounded-xl bg-[var(--v-bg)] p-4"><h3 className="text-sm font-semibold">{door.name}</h3><p className="mt-2 text-xs leading-relaxed text-[var(--v-muted-foreground)]">{door.detail}</p><Link href={door.href} className="mt-3 inline-flex min-h-10 items-center text-xs font-semibold text-[var(--v-primary)]">{door.action} →</Link></article>)}</div><p className="mt-4 text-xs text-[var(--v-muted-foreground)]">These records feed Money, Stock, Cash, Menu, Forecasts, Ask LEVIII and Reports. Missing information stays labelled.</p></section>}
      <Licences block={b.licences as LicencesBlock} />
      <div className="grid gap-3 md:grid-cols-3">
        <Settings block={b.settings as SettingsBlock} />
        <Till block={b.till_connection as InfoBlock} />
        <DataTrust block={b.data_trust as DataTrustBlock} />
      </div>
    </div>
  );
}

function Licences({ block }: { block: LicencesBlock }) {
  return (
    <BlockFrame title={T.licences} block={block}>{() => (<>
      {block.items.length === 0 ? <Empty>No licences entered yet. Add them so you hear before one runs out.</Empty> : (
        <ul className="divide-y divide-[var(--v-border)] text-xs">
          {block.items.map((l) => (
            <li key={l.name} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <span><b>{l.name}</b><span className="block text-[11px] text-[var(--v-muted-foreground)]">{l.issuer}</span></span>
              <span className="text-right"><Pill tone={LICENCE_TONE[l.status] ?? "quiet"}>{l.word}</Pill><span className="mt-0.5 block text-[11px] text-[var(--v-muted-foreground)]">{l.days_left < 0 ? `ran out ${shortDay(l.expires_on)}` : `${shortDay(l.expires_on)} · ${plural(l.days_left, "day")} left`}</span></span>
            </li>
          ))}
        </ul>
      )}
    </>)}</BlockFrame>
  );
}

function Settings({ block }: { block: SettingsBlock }) {
  const { fields, openTargets } = useSettings();
  return (
    <BlockFrame title={T.settings} block={block}>{() => (<>
      <Stat label="Targets you set" value={`${block.changed} of ${block.total}`} note={block.chosen ? "the rest use our defaults" : "all of them use our defaults for now"} />
      <Link href="/settings" className="mt-3 inline-flex min-h-10 items-center text-[11px] font-bold text-[var(--v-primary)]">All targets & alert settings →</Link>
      {fields && <button type="button" onClick={openTargets} className="mt-3 min-h-10 text-[11px] font-bold text-[var(--v-primary)]">Review my targets →</button>}
    </>)}</BlockFrame>
  );
}

function Till({ block }: { block: InfoBlock }) {
  return (
    <BlockFrame title={T.till_connection} block={block} quiet>{() => (<>
      <p className="text-sm font-semibold">{block.word}</p>
      <Note>{block.source === "direct" ? "Your sales and costs are recorded here, so there is no other system to wait for." : block.reconciled ? "The deliveries from your till match your records." : "The deliveries from your till have not been matched to your records yet."}</Note>
    </>)}</BlockFrame>
  );
}

function DataTrust({ block }: { block: DataTrustBlock }) {
  return (
    <BlockFrame title={T.data_trust} block={block}>{() => (<>
      <p className="font-display text-xl font-semibold tracking-[-0.03em]">{Number(block.costs_known_pct.toFixed(1))}%</p>
      <div role="progressbar" aria-label="Dishes with a cost" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(block.costs_known_pct)} className="mt-1.5 h-2 overflow-hidden rounded-full bg-[var(--v-muted)]">
        <div className="h-full rounded-full bg-[var(--v-primary)]" style={{ width: `${block.costs_known_pct}%` }} />
      </div>
      <Note>{block.to_fix === 0 ? `All ${block.dishes} dishes have a saved ingredient cost. Contributions use those saved costs; payroll and other expenses are reviewed separately.` : `${plural(block.to_fix, "dish")} of ${block.dishes} ${block.to_fix === 1 ? "has" : "have"} no ingredient cost, so ${block.to_fix === 1 ? "its" : "their"} profit looks bigger than it is.`}</Note>
    </>)}</BlockFrame>
  );
}
