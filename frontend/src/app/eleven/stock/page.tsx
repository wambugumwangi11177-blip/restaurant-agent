"use client";

import { useEffect, useState } from "react";
import OwnerShell from "@/components/eleven/OwnerShell";
import { GlassCard, SectionLabel, WaitingNotice } from "@/components/eleven/EmptyPanels";
import { useOwnerFeed } from "@/components/eleven/OwnerFeed";
import api from "@/lib/api";

export default function ElevenStockPage() {
  const { data, error } = useOwnerFeed();
  const [runout, setRunout] = useState<{ name?: string; days_left?: number; unit?: string }[]>([]);

  useEffect(() => {
    api.get("/api/v1/eleven/outcomes/stock").then((r) => setRunout(r.data.runout_within_two_weeks ?? [])).catch(() => undefined);
  }, []);
  const close = data?.events?.find((event) => event.kind === "close");
  const gap = close?.headline?.includes("off the books") ? close.headline : "";

  return (
    <OwnerShell title="Stock">
      {!data && !error && <p className="text-sm text-zinc-400">Loading…</p>}
      {data && (
        <>
          <SectionLabel>May run out (14 days)</SectionLabel>
          <GlassCard>
            {runout.length === 0 ? (
              <WaitingNotice>No items projected to run out from recorded usage.</WaitingNotice>
            ) : (
              <ul className="space-y-1 text-sm text-zinc-300">
                {runout.map((row) => (
                  <li key={row.name}>{row.name} — about {row.days_left} days ({row.unit})</li>
                ))}
              </ul>
            )}
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
