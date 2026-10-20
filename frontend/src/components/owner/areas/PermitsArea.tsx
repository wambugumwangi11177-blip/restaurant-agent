"use client";
import { BLOCK_TITLES } from "@/lib/owner/blocks";
import { plural, shortDay } from "@/lib/owner/format";
import type { DataTrustBlock, InfoBlock, LicencesBlock, SettingsBlock } from "@/lib/owner/areaTypes";
import { useSettings } from "@/components/owner/settings/SettingsProvider";
import type { Area } from "@/lib/owner/types";
import { BlockFrame, Empty, Note, Pill, Stat } from "./ui";

const T = BLOCK_TITLES.permits;
const LICENCE_TONE: Record<string, "good" | "warn" | "bad"> = { ok: "good", expiring: "warn", expired: "bad" };

export default function PermitsArea({ area }: { area: Area }) {
  const b = area.blocks;
  return (
    <div className="space-y-3">
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
      <Note>{block.to_fix === 0 ? `All ${block.dishes} dishes have an ingredient cost, so what you keep on each is real.` : `${plural(block.to_fix, "dish")} of ${block.dishes} ${block.to_fix === 1 ? "has" : "have"} no ingredient cost, so ${block.to_fix === 1 ? "its" : "their"} profit looks bigger than it is.`}</Note>
    </>)}</BlockFrame>
  );
}
