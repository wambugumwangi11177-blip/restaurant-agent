"use client";

import OwnerShell from "@/components/eleven/OwnerShell";
import { GlassCard, SectionLabel, WaitingNotice } from "@/components/eleven/EmptyPanels";
import { useElevenEmpty } from "@/components/eleven/useElevenEmpty";

export default function ElevenStockPage() {
  const { loading } = useElevenEmpty();
  return (
    <OwnerShell title="Stock">
      <SectionLabel>To order</SectionLabel>
      {loading ? (
        <p className="text-sm text-zinc-400">Loading…</p>
      ) : (
        <GlassCard>
          <WaitingNotice>
            No draft orders yet. Suggestions appear after recipes and an opening count are recorded.
          </WaitingNotice>
          <p className="mt-3 text-xs text-zinc-500">
            Handover gaps will show as &quot;Check this&quot; — never as proof of wrongdoing.
          </p>
        </GlassCard>
      )}
      <SectionLabel>Missing stock</SectionLabel>
      <GlassCard>
        <WaitingNotice>No gaps recorded — nothing to check yet.</WaitingNotice>
      </GlassCard>
    </OwnerShell>
  );
}
