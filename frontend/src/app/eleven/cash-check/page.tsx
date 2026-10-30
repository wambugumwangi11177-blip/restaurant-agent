"use client";

import OwnerShell from "@/components/eleven/OwnerShell";
import { GlassCard, WaitingNotice } from "@/components/eleven/EmptyPanels";

export default function ElevenCashCheckPage() {
  return (
    <OwnerShell title="Cash Check">
      <GlassCard>
        <WaitingNotice>Is your money where it should be? — shift closes and drawer counts will show here once staff start entering them.</WaitingNotice>
        <p className="mt-4 text-xs text-zinc-400">
          A gap is something to check. It is never proof that a person did something wrong.
        </p>
      </GlassCard>
    </OwnerShell>
  );
}
