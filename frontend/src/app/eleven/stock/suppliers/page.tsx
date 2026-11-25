"use client";

import OwnerShell from "@/components/eleven/OwnerShell";
import ExplainedCard, { type Verdict } from "@/components/eleven/charts/ExplainedCard";
import { useOwnerGet } from "@/hooks/useOwnerV11";

export default function StockSuppliersPage() {
  const { data } = useOwnerGet<{
    rows?: { name: string; lead_days: number; on_time_pct: number; price_jump?: boolean }[];
    has_data?: boolean;
    empty?: string;
  }>("/api/v1/eleven/stock/suppliers", []);
  const rows = data?.rows ?? [];
  const jumps = rows.filter((r) => r.price_jump).length;
  const worst = [...rows].sort((a, b) => a.on_time_pct - b.on_time_pct)[0];

  const verdict: Verdict | undefined = worst
    ? worst.on_time_pct < 80
      ? { tone: "watch", text: `${worst.name} is under 80% on time.` }
      : jumps
        ? { tone: "watch", text: `${jumps} supplier${jumps === 1 ? "" : "s"} flagged for a price jump.` }
        : { tone: "good", text: "Deliveries are mostly on time." }
    : undefined;

  return (
    <OwnerShell title="Suppliers">
      <ExplainedCard
        title="Supplier reliability"
        headline={worst ? `${worst.name}: ${worst.on_time_pct}% on time, ${worst.lead_days} lead days` : undefined}
        verdict={data?.has_data ? verdict : undefined}
        what="On-time %, lead days, and a price-jump flag from recent invoices."
        why="On time = received on or before the day you expected. Lead days are from your PO history."
        freshness="As entered · from deliveries and invoices"
        hasData={!!data?.has_data}
        emptyHint={data?.empty ?? "Starts when deliveries are logged."}
      >
        <ul className="space-y-2 text-sm">
          {rows.map((r) => (
            <li key={r.name} className="owner-glass-inner flex flex-wrap justify-between gap-2 px-3 py-2">
              <span className="text-zinc-100">{r.name}</span>
              <span className="text-xs text-zinc-400">
                {r.on_time_pct}% on time · {r.lead_days}d lead
                {r.price_jump ? " · price jump flagged" : ""}
              </span>
            </li>
          ))}
        </ul>
      </ExplainedCard>
    </OwnerShell>
  );
}