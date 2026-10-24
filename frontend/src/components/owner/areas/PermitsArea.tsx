"use client";
import { FormEvent, useState } from "react";
import api from "@/lib/api";
import { BLOCK_TITLES } from "@/lib/owner/blocks";
import { OWNER_DATA_CHANGED } from "@/lib/owner/useOwnerHome";
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
  return (<>
    <BlockFrame title={T.licences} block={block}>{() => (<>
      {block.items.length === 0 ? <Empty>No licences entered yet. Add them so you hear before one runs out.</Empty> : (
        <ul className="divide-y divide-[var(--v-border)] text-xs">
          {block.items.map((l) => (
            <li key={l.id ?? l.name} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <span><b>{l.name}</b><span className="block text-[11px] text-[var(--v-muted-foreground)]">{l.issuer}</span></span>
              <span className="text-right">
                <Pill tone={LICENCE_TONE[l.status] ?? "quiet"}>{l.word}</Pill>
                <span className="mt-0.5 block text-[11px] text-[var(--v-muted-foreground)]">{l.days_left < 0 ? `ran out ${shortDay(l.expires_on)}` : `${shortDay(l.expires_on)} · ${plural(l.days_left, "day")} left`}</span>
                {l.id != null && <LicenceEdit id={l.id} name={l.name} issuer={l.issuer} expires={l.expires_on} />}
              </span>
            </li>
          ))}
        </ul>
      )}
    </>)}</BlockFrame>
    <LicenceForm />
  </>);
}

function Settings({ block }: { block: SettingsBlock }) {
  const { fields, openTargets } = useSettings();
  return (
    <BlockFrame title={T.settings} block={block}>{() => (<>
      <Stat label="Targets you set" value={`${block.changed} of ${block.total}`} note={block.chosen ? "the rest use our defaults" : "all of them use our defaults for now"} />
      {fields && <button type="button" onClick={openTargets} className="mt-3 min-h-10 text-[11px] font-bold text-[var(--v-primary)]">Review my targets →</button>}
      <SettingsHistory />
    </>)}</BlockFrame>
  );
}

const field = "mt-1 block min-h-11 w-full rounded-lg border border-[var(--v-border)] bg-[var(--v-card)] px-3 text-sm";

function LicenceEdit({ id, name, issuer, expires }: { id: number; name: string; issuer: string; expires: string }) {
  const [open, setOpen] = useState(false);
  const [nextName, setNextName] = useState(name);
  const [nextIssuer, setNextIssuer] = useState(issuer);
  const [nextExpires, setNextExpires] = useState(expires.slice(0, 10));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(""); setSaved("");
    try {
      await api.patch(`/api/v1/owner/money/licences/${id}`, { name: nextName, issuer: nextIssuer, expires_on: nextExpires });
      setSaved("Licence updated.");
      window.dispatchEvent(new Event(OWNER_DATA_CHANGED));
    } catch {
      setError("Could not update that licence.");
    } finally { setBusy(false); }
  };
  if (!open) return <button type="button" onClick={() => setOpen(true)} className="mt-1 min-h-10 text-[11px] font-bold text-[var(--v-primary)]">Edit</button>;
  return (
    <form onSubmit={save} className="mt-2 space-y-2 text-left">
      <label className="block text-[11px]">Name<input className={field} value={nextName} onChange={(e) => setNextName(e.target.value)} required /></label>
      <label className="block text-[11px]">Authority<input className={field} value={nextIssuer} onChange={(e) => setNextIssuer(e.target.value)} /></label>
      <label className="block text-[11px]">Expires<input type="date" className={field} value={nextExpires} onChange={(e) => setNextExpires(e.target.value)} required /></label>
      <button disabled={busy} className="min-h-10 rounded-lg bg-[var(--v-primary)] px-3 text-[11px] font-bold text-[var(--v-primary-foreground)]">{busy ? "Saving…" : "Save changes"}</button>
      {saved && <p role="status" className="text-[11px] text-[var(--v-good)]">{saved}</p>}
      {error && <p role="alert" className="text-[11px] text-[var(--v-warn)]">{error}</p>}
    </form>
  );
}

function LicenceForm() {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [issuer, setIssuer] = useState("");
  const [expires, setExpires] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(""); setSaved("");
    try {
      await api.post("/api/v1/owner/money/licences", { name, issuer, expires_on: expires });
      setSaved(`${name} is on the licence list and in Coming up.`);
      setName(""); setIssuer(""); setExpires("");
      window.dispatchEvent(new Event(OWNER_DATA_CHANGED));
    } catch {
      setError("Could not save that licence. Check the expiry date.");
    } finally { setBusy(false); }
  };
  if (!open) return <button type="button" onClick={() => setOpen(true)} className="min-h-10 text-[11px] font-bold text-[var(--v-primary)]">Add a licence</button>;
  return (
    <form onSubmit={save} className="space-y-3 rounded-lg border border-[var(--v-border)] bg-[var(--v-bg)] p-3.5">
      <h4 className="text-[11px] font-bold uppercase tracking-[0.12em] text-[var(--v-muted-foreground)]">Add a licence</h4>
      <label className="block text-xs">Name<input className={field} value={name} onChange={(e) => setName(e.target.value)} required /></label>
      <label className="block text-xs">Authority<input className={field} value={issuer} onChange={(e) => setIssuer(e.target.value)} /></label>
      <label className="block text-xs">Expires<input type="date" className={field} value={expires} onChange={(e) => setExpires(e.target.value)} required /></label>
      <button disabled={busy} className="min-h-10 rounded-lg bg-[var(--v-primary)] px-3 text-[11px] font-bold text-[var(--v-primary-foreground)]">{busy ? "Saving…" : "Save licence"}</button>
      {saved && <p role="status" className="text-xs text-[var(--v-good)]">{saved}</p>}
      {error && <p role="alert" className="text-xs text-[var(--v-warn)]">{error}</p>}
    </form>
  );
}

function SettingsHistory() {
  const [rows, setRows] = useState<{ field: string; old_value: string; new_value: string; changed_at: string }[] | null>(null);
  const [error, setError] = useState("");
  const load = () => {
    api.get("/api/v1/owner/settings/history").then((r) => setRows(r.data.history ?? [])).catch(() => setError("Could not load the history of your targets."));
  };
  return (
    <div className="mt-2">
      {rows == null ? <button type="button" onClick={load} className="min-h-10 text-[11px] font-bold text-[var(--v-primary)]">History of target changes</button> : (
        rows.length === 0 ? <p className="text-[11px] text-[var(--v-muted-foreground)]">No target has been changed yet.</p> : (
          <ul className="space-y-1 text-[11px]">{rows.slice(0, 8).map((r, i) => <li key={`${r.field}-${i}`}>{r.field}: {String(r.old_value)} → {String(r.new_value)}</li>)}</ul>
        )
      )}
      {error && <p role="alert" className="text-[11px] text-[var(--v-warn)]">{error}</p>}
    </div>
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
