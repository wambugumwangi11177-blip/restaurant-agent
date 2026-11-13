"use client";

import { useEffect, useState } from "react";
import OwnerShell from "@/components/eleven/OwnerShell";
import Link from "next/link";
import { GlassCard, SectionLabel, WaitingNotice } from "@/components/eleven/EmptyPanels";
import api from "@/lib/api";

export default function ElevenSettingsPage() {
  const [qty, setQty] = useState("5");
  const [saved, setSaved] = useState("");

  useEffect(() => {
    api.get("/api/v1/store/policy").then((response) => {
      setQty(String(response.data.spoilage_approval_qty ?? 5));
    }).catch(() => setSaved(""));
  }, []);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    await api.put("/api/v1/store/policy", { spoilage_approval_qty: Number(qty) });
    setSaved("Saved. Smaller amounts are only reported.");
  }

  return (
    <OwnerShell title="Settings">
      <SectionLabel>Your till</SectionLabel>
      <GlassCard>
        <Link href="/eleven/settings/till" className="inline-flex min-h-11 items-center text-sm text-white underline">Review QuickSell receipt and parser evidence</Link>
      </GlassCard>
      <SectionLabel>Permits</SectionLabel>
      <GlassCard>
        <WaitingNotice>Add your fire, food handling, and liquor licences to see days left and reminders.</WaitingNotice>
      </GlassCard>
      <SectionLabel>Your numbers</SectionLabel>
      <GlassCard>
        <form onSubmit={save} className="space-y-3">
          <label className="block text-sm">Waste or a count gap that waits for you
            <input inputMode="decimal" value={qty} onChange={(event) => setQty(event.target.value)} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3" />
          </label>
          <button type="submit" className="min-h-11 rounded-full bg-white px-4 font-semibold text-black">Save</button>
          {saved && <p className="text-sm text-zinc-300">{saved}</p>}
        </form>
        <WaitingNotice>Margin and cash-gap reminders stay quiet until the till is live.</WaitingNotice>
      </GlassCard>
    </OwnerShell>
  );
}
