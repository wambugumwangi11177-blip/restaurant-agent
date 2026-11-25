"use client";

import OwnerShell from "@/components/eleven/OwnerShell";
import OwnerChartCard from "@/components/eleven/charts/OwnerChartCard";
import { useOwnerGet } from "@/hooks/useOwnerV11";
import { formatKes } from "@/lib/formatKes";
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

type LineRow = {
  name: string;
  supplier: string;
  kes_per_unit: number;
  trend: { at: string; kes_per_unit: number }[];
};

export default function SupplierPricesPage() {
  const { data } = useOwnerGet<{ lines?: LineRow[]; has_sales?: boolean; empty?: string }>(
    "/api/v1/eleven/money/supplier-prices",
    [],
  );
  const lines = data?.lines ?? [];

  return (
    <OwnerShell title="Supplier prices">
      <div className="owner-premium-stack space-y-4">
        {lines.length === 0 && <p className="text-sm text-zinc-400">{data?.empty ?? "No invoice prices yet."}</p>}
        {lines.map((row) => (
          <OwnerChartCard
            key={row.name}
            title={row.name}
            caption={row.supplier ? `Supplier: ${row.supplier}` : "Last unit from invoices"}
            detailHref={undefined}
            hasData={row.trend.length > 0}
            emptyHint="No history yet."
          >
            <p className="text-sm text-zinc-300 mb-2">Latest: {formatKes(row.kes_per_unit)}</p>
            <ResponsiveContainer width="100%" height={120}>
              <LineChart data={row.trend}>
                <XAxis dataKey="at" tick={{ fill: "#a1a1aa", fontSize: 9 }} />
                <YAxis hide />
                <Tooltip formatter={(v) => formatKes(Number(v))} />
                <Line type="monotone" dataKey="kes_per_unit" stroke="#8b7d72" dot />
              </LineChart>
            </ResponsiveContainer>
          </OwnerChartCard>
        ))}
      </div>
    </OwnerShell>
  );
}