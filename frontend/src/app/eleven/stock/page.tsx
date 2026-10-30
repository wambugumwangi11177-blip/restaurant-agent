"use client";

import OwnerShell from "@/components/eleven/OwnerShell";
import { GlassCard, SectionLabel, WaitingNotice } from "@/components/eleven/EmptyPanels";
import { useElevenEmpty } from "@/components/eleven/useElevenEmpty";

export default function ElevenStockPage() {
  const { loading } = useElevenEmpty();
  return (
    <OwnerShell title="Stock">
      <SectionLabel>To order</SectionLabel>
      <div className="owner-glass-panel mb-3 rounded-2xl border border-white/10 bg-white/5 px-3 py-2 text-xs text-zinc-300">
        Based on 0 of 0 dishes. Dishes without a recipe are not included.
      </div>
      {loading ? (
        <p className="text-sm text-zinc-400">Loading…</p>
      ) : (
        <GlassCard>
          <WaitingNotice>
            No draft orders yet. When Jack (storekeeper) adds suppliers and opening stock, LEVIII will suggest what to order here.
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
