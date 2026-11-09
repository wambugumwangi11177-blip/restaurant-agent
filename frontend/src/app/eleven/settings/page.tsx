"use client";

import OwnerShell from "@/components/eleven/OwnerShell";
import Link from "next/link";
import { GlassCard, SectionLabel, WaitingNotice } from "@/components/eleven/EmptyPanels";

export default function ElevenSettingsPage() {
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
        <WaitingNotice>Thresholds (margin floor, cash gap, urgent alerts) use defaults until you save your own.</WaitingNotice>
      </GlassCard>
    </OwnerShell>
  );
}
