"use client";

import OwnerShell from "@/components/eleven/OwnerShell";
import { GlassCard, SectionLabel, SolidNumberCard, WaitingNotice } from "@/components/eleven/EmptyPanels";
import { useElevenEmpty } from "@/components/eleven/useElevenEmpty";

export default function ElevenMoneyPage() {
  const { loading, empty } = useElevenEmpty();
  return (
    <OwnerShell title="My Money">
      {loading ? (
        <p className="text-sm text-zinc-400">Loading…</p>
      ) : (
        <>
          <SolidNumberCard
            title="What you kept this month"
            body={empty ? "Waiting on sales" : "See reports when ready"}
            hint={empty ? "Includes costs once you add rent and monthly bills" : undefined}
          />
          <SectionLabel>Your profit and loss</SectionLabel>
          <GlassCard>
            <WaitingNotice>
              {empty
                ? "No sales recorded yet. Connect your till, then enter wages and running costs to see what you kept in plain words."
                : "Building your first month view — keep entering costs as they happen."}
            </WaitingNotice>
          </GlassCard>
        </>
      )}
    </OwnerShell>
  );
}
