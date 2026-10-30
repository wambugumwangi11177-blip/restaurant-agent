"use client";

import OwnerShell from "@/components/eleven/OwnerShell";
import { GlassCard, WaitingNotice } from "@/components/eleven/EmptyPanels";

export default function ElevenAlertsPage() {
  return (
    <OwnerShell title="Alerts">
      <p className="mb-3 text-xs text-zinc-400">
        Up to 5 urgent alerts a day, quiet after 10 pm. You can change this in Settings.
      </p>
      <GlassCard>
        <WaitingNotice>No urgent alerts — nothing needs you right now.</WaitingNotice>
      </GlassCard>
    </OwnerShell>
  );
}
