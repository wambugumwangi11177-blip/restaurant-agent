"use client";

import OwnerShell from "@/components/eleven/OwnerShell";
import ExplainedCard from "@/components/eleven/charts/ExplainedCard";
import { useOwnerGet } from "@/hooks/useOwnerV11";

import { plural } from "@/lib/pluralize";

function plateLabel(n?: number) {
  if (n == null) return "—";
  return plural(n, "plate");
}

export default function StockPrepPage() {
  const { data } = useOwnerGet<{ items?: { dish?: string; name?: string; plates?: number }[]; has_data?: boolean; empty?: string }>(
    "/api/v1/eleven/stock/prep",
    [],
  );
  const items = data?.items ?? [];
  const totalPlates = items.reduce((a, it) => a + (it.plates ?? 0), 0);

  return (
    <OwnerShell title="Prep">
      <ExplainedCard
        title="Today's prep"
        headline={items.length ? `${plural(items.length, "dish")} · about ${plural(totalPlates, "plate")}` : undefined}
        verdict={{ tone: "neutral", text: "Check each line before service." }}
        what="Forecast plates from recent same-weekdays, times the recipe — today's checklist."
        why="Expected demand from your recent sales pattern, not a promise."
        freshness="Assumption · from recent sales"
        hasData={!!data?.has_data}
        emptyHint={data?.empty ?? "Starts when dishes sell."}
      >
        <ul className="space-y-2 text-sm">
          {items.map((it, i) => (
            <li key={i} className="owner-glass-inner flex justify-between gap-2 px-3 py-2">
              <span>{it.dish || it.name}</span>
              <span className="text-zinc-400">{plateLabel(it.plates)}</span>
            </li>
          ))}
        </ul>
      </ExplainedCard>
    </OwnerShell>
  );
}