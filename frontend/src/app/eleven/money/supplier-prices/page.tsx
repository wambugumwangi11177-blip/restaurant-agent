"use client";

import OwnerShell from "@/components/eleven/OwnerShell";
import ExplainedCard, { type Verdict } from "@/components/eleven/charts/ExplainedCard";
import { useOwnerGet } from "@/hooks/useOwnerV11";
import { pctChange } from "@/lib/chartFormat";
import { formatKes } from "@/lib/formatKes";
import { Line, LineChart, ResponsiveContainer, YAxis } from "recharts";

type LineRow = {
  name: string;
  supplier: string;
  kes_per_unit: number;
  trend: { at: string; kes_per_unit: number }[];
  price_jump?: boolean;
};

function trendChange(row: LineRow): { pct: number | null; jump: boolean } {
  const trend = row.trend;
  const now = row.kes_per_unit ?? trend[trend.length - 1]?.kes_per_unit ?? 0;
  const ago = trend.length > 1 ? trend[0]?.kes_per_unit ?? now : now;
  const pct = pctChange(now, ago);
  const jump = row.price_jump ?? (pct != null && pct > 10);
  return { pct, jump };
}

export default function SupplierPricesPage() {
  const { data } = useOwnerGet<{ lines?: LineRow[]; has_sales?: boolean; empty?: string }>(
    "/api/v1/eleven/money/supplier-prices",
    [],
  );
  const lines = data?.lines ?? [];
  const jumps = lines.filter((r) => trendChange(r).jump).length;

  const verdict: Verdict =
    jumps > 0
      ? { tone: "watch", text: `${jumps} item${jumps === 1 ? "" : "s"} jumped more than 10%.` }
      : lines.length
        ? { tone: "good", text: "Prices steady on recent invoices." }
        : { tone: "neutral", text: "No invoice history yet." };

  return (
    <OwnerShell title="Supplier prices">
      <ExplainedCard
        title="Supplier prices"
        headline={jumps ? `${jumps} items jumped more than 10%` : lines.length ? "Prices steady" : undefined}
        verdict={lines.length ? verdict : undefined}
        what="Each row: item name, change vs ~30 days ago, and a tiny price sparkline."
        why="Unit price from invoices. A jump is against the oldest point in the trend."
        freshness="As entered · from supplier invoices"
        hasData={lines.length > 0}
        emptyHint={data?.empty ?? "No invoice prices yet."}
      >
        <ul className="space-y-3 text-sm">
          {lines.map((row) => {
            const { pct, jump } = trendChange(row);
            return (
              <li key={row.name} className="owner-glass-inner flex items-center gap-3 px-3 py-2">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-zinc-100">{row.name}</p>
                  <p className="text-xs text-zinc-500">{row.supplier || "Supplier"}</p>
                  <p className="mt-0.5 text-xs text-zinc-300">
                    {formatKes(row.kes_per_unit)}
                    {pct != null ? (
                      <span className={jump ? "text-amber-300" : "text-zinc-500"}>
                        {" "}
                        · {pct > 0 ? "+" : ""}
                        {pct}% vs first invoice
                      </span>
                    ) : null}
                    {jump ? <span className="text-amber-300"> · jump</span> : null}
                  </p>
                </div>
                <div className="h-8 w-20 shrink-0">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={row.trend}>
                      <YAxis hide domain={["dataMin", "dataMax"]} />
                      <Line type="monotone" dataKey="kes_per_unit" stroke={jump ? "#fbbf24" : "#8b7d72"} strokeWidth={1.5} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </li>
            );
          })}
        </ul>
      </ExplainedCard>
    </OwnerShell>
  );
}