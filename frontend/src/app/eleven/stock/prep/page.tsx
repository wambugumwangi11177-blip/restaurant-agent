"use client";

import OwnerShell from "@/components/eleven/OwnerShell";
import { useOwnerGet } from "@/hooks/useOwnerV11";

export default function StockPrepPage() {
  const { data } = useOwnerGet<{ items?: { dish?: string; name?: string; plates?: number }[]; has_data?: boolean; empty?: string }>("/api/v1/eleven/stock/prep", []);
  return (
    <OwnerShell title="Prep">
      <ul className="space-y-2 text-sm">
        {(data?.items ?? []).map((it: { dish?: string; name?: string; plates?: number }, i: number) => (
          <li key={i} className="owner-glass-panel px-3 py-2">
            {it.dish || it.name} — {it.plates ?? "—"} plates
          </li>
        ))}
        {!data?.has_data && <p className="text-zinc-400">{data?.empty}</p>}
      </ul>
    </OwnerShell>
  );
}