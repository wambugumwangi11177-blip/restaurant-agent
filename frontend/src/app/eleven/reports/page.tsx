"use client";

import OwnerShell from "@/components/eleven/OwnerShell";
import { GlassCard, WaitingNotice } from "@/components/eleven/EmptyPanels";

export default function ElevenReportsPage() {
  return (
    <OwnerShell title="Reports">
      <GlassCard>
        <WaitingNotice>Today&apos;s close, week, month, and year reports unlock after your first sales and cost entries.</WaitingNotice>
      </GlassCard>
    </OwnerShell>
  );
}
