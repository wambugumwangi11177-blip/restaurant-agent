"use client";

import OwnerShell from "@/components/eleven/OwnerShell";
import { DayOneChecklist, GlassCard, SectionLabel, SolidNumberCard, WaitingNotice } from "@/components/eleven/EmptyPanels";
import { useElevenEmpty } from "@/components/eleven/useElevenEmpty";

export default function ElevenHomePage() {
  const { loading, empty, provenance } = useElevenEmpty();
  const tillLine = provenance?.latest_order_at
    ? "Your till updated recently"
    : "Waiting on your till — connect Quick Sell to see today's sales";

  return (
    <OwnerShell title="Home">
      {loading ? (
        <p className="text-sm text-zinc-400">Loading…</p>
      ) : empty ? (
        <>
          <SolidNumberCard title="Today's pulse" body="Money match" hint={tillLine} />
          <SectionLabel>What's costing you money</SectionLabel>
          <GlassCard>
            <p className="font-medium">Add your rent and monthly bills</p>
            <p className="mt-2 text-xs text-zinc-400">Still learning your restaurant — no costs entered yet.</p>
          </GlassCard>
          <SectionLabel>Getting started</SectionLabel>
          <GlassCard>
            <DayOneChecklist />
          </GlassCard>
          {provenance?.notice && (
            <p className="mt-4 text-xs text-zinc-500">{provenance.notice}</p>
          )}
        </>
      ) : (
        <>
          <SolidNumberCard
            title="Today's pulse"
            body="Sales connected"
            hint={tillLine}
          />
          <SectionLabel>What's costing you money</SectionLabel>
          <GlassCard>
            <WaitingNotice>LEVIII will surface leaks here once enough sales and costs are recorded.</WaitingNotice>
          </GlassCard>
        </>
      )}
    </OwnerShell>
  );
}
