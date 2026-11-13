"use client";

import OwnerShell from "@/components/eleven/OwnerShell";
import { GlassCard, SectionLabel, WaitingNotice } from "@/components/eleven/EmptyPanels";
import { useOwnerFeed } from "@/components/eleven/OwnerFeed";

export default function ElevenStockPage() {
  const { data, error } = useOwnerFeed();
  const close = data?.events?.find((event) => event.kind === "close");
  const gap = close?.headline?.includes("off the books") ? close.headline : "";

  return (
    <OwnerShell title="Stock">
      {!data && !error && <p className="text-sm text-zinc-400">Loading…</p>}
      {data && (
        <>
          <SectionLabel>To order</SectionLabel>
          <GlassCard>
            <WaitingNotice>
              {data.till_live
                ? "Sales are coming in from the till."
                : "Waiting for the till. Nothing to order until QuickSell is sending sales."}
            </WaitingNotice>
            <p className="mt-3 text-xs text-zinc-500">
              A gap is something to check.
            </p>
          </GlassCard>
          <SectionLabel>Missing stock</SectionLabel>
          <GlassCard>
            <WaitingNotice>
              {gap || "No count is in yet, so there is no gap to check."}
            </WaitingNotice>
          </GlassCard>
        </>
      )}
    </OwnerShell>
  );
}
