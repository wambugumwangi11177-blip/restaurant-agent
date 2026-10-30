"use client";

import OwnerShell from "@/components/eleven/OwnerShell";
import { GlassCard, SectionLabel, WaitingNotice } from "@/components/eleven/EmptyPanels";

export default function ElevenSettingsPage() {
  return (
    <OwnerShell title="Settings">
      <SectionLabel>Permits</SectionLabel>
      <GlassCard>
        <WaitingNotice>Add your fire, food handling, and liquor licences to see days left and reminders.</WaitingNotice>
      </GlassCard>
      <SectionLabel>Your numbers</SectionLabel>
      <GlassCard>
        <WaitingNotice>Thresholds (margin floor, cash gap, urgent alerts) use defaults until you save your own.</WaitingNotice>
      </GlassCard>
    </OwnerShell>
  );
}
