"use client";

import OwnerShell from "@/components/eleven/OwnerShell";
import { GlassCard, WaitingNotice } from "@/components/eleven/EmptyPanels";

export default function ElevenAskPage() {
  return (
    <OwnerShell title="Ask">
      <GlassCard>
        <WaitingNotice>
          Ask LEVIII once your till and stock are connected. Example: &quot;What did we sell yesterday?&quot; needs sales data — we will not invent numbers.
        </WaitingNotice>
        <p className="mt-3 text-[10px] font-bold uppercase tracking-widest text-zinc-500">Written by AI (when available)</p>
      </GlassCard>
      <div className="mt-4 flex flex-wrap gap-2 opacity-60">
        {["What did we sell yesterday?", "Why was Tuesday down?", "What should I fix this week?"].map((q) => (
          <span key={q} className="rounded-full border border-white/20 px-3 py-2 text-xs">
            {q}
          </span>
        ))}
      </div>
    </OwnerShell>
  );
}
