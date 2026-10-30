"use client";

import OwnerShell from "@/components/eleven/OwnerShell";
import { GlassCard, WaitingNotice } from "@/components/eleven/EmptyPanels";

export default function ElevenSalesDishesPage() {
  return (
    <OwnerShell title="Sales & Dishes">
      <GlassCard>
        <WaitingNotice>Waiting on your till. Menu groups and price ideas appear after sales and recipe costs are in.</WaitingNotice>
      </GlassCard>
    </OwnerShell>
  );
}
