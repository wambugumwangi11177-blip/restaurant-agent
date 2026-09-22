"use client";

import { useEffect, useState } from "react";
import { ArrowLeft, Database, LineChart, Table2 } from "lucide-react";
import Link from "next/link";
import api from "@/lib/api";
import { isVerifiedVibandaSource } from "@/lib/vibandaSource";
import VibandaForecast from "@/components/vibanda/VibandaForecast";

type View = { title: string; description: string; source: string; metrics: string[]; mode: "trend" | "timeline" | "status" | "exceptions"; visual: string; table: string; note: string };
type Connection = { state?: string; records?: number | null; reconciled?: boolean };

function EmptyMetric({ label }: { label: string }) { return <div className="rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-4"><p className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--v-muted-foreground)]">{label}</p><p className="font-display mt-3 text-2xl font-semibold">—</p><p className="mt-2 text-xs text-[var(--v-muted-foreground)]">Waiting for verified records</p></div>; }

export default function VibandaAreaClient({ areaKey, view }: { areaKey: string; view: View }) {
  const [sourceVerified, setSourceVerified] = useState<boolean | null>(null);
  useEffect(() => {
    let active = true;
    api.get<{ data_provenance?: { source_connection?: Connection } }>("/api/v1/overview/today?period=today", { timeout: 15000 })
      .then((response) => { if (active) setSourceVerified(isVerifiedVibandaSource(response.data?.data_provenance?.source_connection)); })
      .catch(() => { if (active) setSourceVerified(false); });
    return () => { active = false; };
  }, []);

  const live = sourceVerified === true;
  const primaryIcon = view.mode === "trend" ? <LineChart size={16} className="text-[var(--v-primary)]"/> : <Table2 size={16} className="text-[var(--v-primary)]"/>;
  const primaryMessage = view.mode === "status" ? "Status details will appear after verified records arrive. No connection state is being guessed." : view.mode === "timeline" ? "Recent activity will appear after verified records arrive. No events are being invented." : view.mode === "exceptions" ? "Important exceptions will appear after verified records arrive. A quiet state will remain simple and confirmed." : "The trend will appear after verified records arrive. No shape or direction is being guessed.";

  return <div className="animate-rise-in max-w-5xl space-y-7"><Link href="/vibanda" className="inline-flex items-center gap-2 text-xs font-semibold text-[var(--v-primary)]"><ArrowLeft size={14}/> Back to overview</Link><div><p className="mb-1 text-[10px] font-bold uppercase tracking-[0.16em] text-[var(--v-muted-foreground)]">Vibanda Village · owner view</p><h1 className="font-display text-[clamp(2rem,4vw,3.25rem)] font-semibold tracking-[-0.045em]">{view.title}<span className="text-[var(--v-primary)]">.</span></h1><p className="mt-3 text-sm text-[var(--v-muted-foreground)]">{view.description}</p></div>
    {!live ? <div className="flex gap-3 rounded-xl border border-[hsl(43_76%_57_/.45)] bg-[hsl(43_76%_57_/.10)] p-5"><Database className="mt-0.5 shrink-0 text-[var(--v-primary)]" size={22}/><div><p className="font-semibold">Waiting for verified MacSoft records</p><p className="mt-1 text-sm text-[var(--v-muted-foreground)]">The page is designed around the live business data path, but no conclusions are shown before the source delivers records.</p><p className="mt-3 text-xs text-[var(--v-muted-foreground)]">Information used: {view.source}</p></div></div> : <div className="flex gap-3 rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-5"><Database className="mt-0.5 shrink-0 text-emerald-400" size={22}/><div><p className="font-semibold">Verified restaurant data connected</p><p className="mt-1 text-sm text-[var(--v-muted-foreground)]">The owner view below uses the approved source. Forecasts appear only when the verified history is sufficient.</p><p className="mt-3 text-xs text-[var(--v-muted-foreground)]">Information used: {view.source}</p></div></div>}
    <section><p className="mb-3 text-[10px] font-bold uppercase tracking-[0.16em] text-[var(--v-muted-foreground)]">At a glance</p><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{view.metrics.map((metric) => <EmptyMetric key={metric} label={metric}/>)}</div></section>
    {!live && <section className="grid gap-4 lg:grid-cols-2"><div className="rounded-xl border border-dashed border-[var(--v-border)] bg-[var(--v-card)] p-5"><div className="flex items-center gap-2">{primaryIcon}<h2 className="font-display text-xl font-semibold">{view.visual}</h2></div><div className="mt-5 flex h-44 items-center justify-center rounded-lg border border-dashed border-[var(--v-border)] text-center"><p className="max-w-xs text-xs text-[var(--v-muted-foreground)]">{primaryMessage}</p></div></div><div className="rounded-xl border border-dashed border-[var(--v-border)] bg-[var(--v-card)] p-5"><div className="flex items-center gap-2"><Table2 size={16} className="text-[var(--v-primary)]"/><h2 className="font-display text-xl font-semibold">{view.table}</h2></div><div className="mt-5 flex h-44 items-center justify-center rounded-lg border border-dashed border-[var(--v-border)] text-center"><p className="max-w-xs text-xs text-[var(--v-muted-foreground)]">No records to list yet. The owner will see the supporting detail here after verified delivery.</p></div></div></section>}
    {live && <VibandaForecast area={areaKey} sourceVerified />}
    <div className="rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-5"><p className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--v-muted-foreground)]">What this page will help the owner know</p><p className="mt-3 text-sm leading-6 text-[var(--v-muted-foreground)]">{view.note}</p></div><div className="rounded-xl border border-dashed border-[var(--v-border)] px-5 py-7 text-center"><p className="text-sm font-semibold">No mock, sample, or local data is being displayed.</p><p className="mt-2 text-xs text-[var(--v-muted-foreground)]">MacSoft remains the system of record.</p></div></div>;
}
