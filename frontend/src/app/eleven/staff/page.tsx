"use client";

import OwnerShell from "@/components/eleven/OwnerShell";
import { GlassCard, SectionLabel, WaitingNotice } from "@/components/eleven/EmptyPanels";

export default function ElevenStaffPage() {
  return (
    <OwnerShell title="Staff">
      <SectionLabel>Today&apos;s roster</SectionLabel>
      <GlassCard>
        <WaitingNotice>Add manager, storekeeper (Jack), kitchen, and accountant accounts to see who entered what.</WaitingNotice>
      </GlassCard>
    </OwnerShell>
  );
}
