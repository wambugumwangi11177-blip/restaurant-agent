"use client";

import { useEffect, useState } from "react";
import { Database, AlertCircle } from "lucide-react";
import api from "@/lib/api";

export default function SourceUnavailable({ title, detail }: { title: string; detail: string }) {
  const [reason, setReason] = useState("Checking the Macsoft connection…");
  useEffect(() => {
    api.get("/api/v1/observer/source-status").then((r) => setReason(r.data.reason || "Macsoft is not connected.")).catch(() => setReason("Macsoft source status could not be reached."));
  }, []);
  return <div className="animate-rise-in max-w-3xl space-y-6"><div><p className="mb-1 text-[10px] font-bold uppercase tracking-[0.16em] text-[var(--v-muted-foreground)]">Vibanda Village · read-only</p><h1 className="font-display text-[clamp(2rem,4vw,3.25rem)] font-semibold tracking-[-0.045em]">{title}<span className="text-[var(--v-primary)]">.</span></h1><p className="mt-3 text-sm text-[var(--v-muted-foreground)]">{detail}</p></div><div className="flex gap-3 rounded-xl border border-[hsl(43_76%_57_/.45)] bg-[hsl(43_76%_57_/.10)] p-5"><Database className="mt-0.5 shrink-0 text-[var(--v-primary)]" size={22}/><div><p className="font-semibold">Macsoft data is unavailable</p><p className="mt-1 text-sm text-[var(--v-muted-foreground)]">{reason}</p></div></div><div className="flex gap-3 rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-5"><AlertCircle className="mt-0.5 shrink-0 text-[var(--v-muted-foreground)]" size={20}/><p className="text-sm text-[var(--v-muted-foreground)]">No local demo or historical operational data is shown as restaurant fact. Macsoft remains the system of record.</p></div></div>;
}
