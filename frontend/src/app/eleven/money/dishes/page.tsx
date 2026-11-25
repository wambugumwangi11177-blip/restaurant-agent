"use client";

import OwnerShell from "@/components/eleven/OwnerShell";
import OwnerChartCard from "@/components/eleven/charts/OwnerChartCard";
import { useOwnerGet } from "@/hooks/useOwnerV11";
import { Bar, BarChart, ScatterChart, Scatter, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { formatKes } from "@/lib/formatKes";

export default function DishesMoneyPage() {
  const { data } = useOwnerGet<{
    has_sales?: boolean;
    empty?: string;
    quadrant?: { x: number; y: number; name?: string }[];
    plate_profit?: { name: string; kes: number }[];
    bestsellers?: { name: string; plates: number }[];
    delivery_vs_dine?: { channel: string; kes: number }[];
    suggestions?: { title?: string; detail?: string }[];
  }>("/api/v1/eleven/money/dishes/summary", []);
  const quad = data?.quadrant ?? [];
  return (
    <OwnerShell title="Dishes">
      <OwnerChartCard title="Menu map" caption="Popular items high on the chart; profitable ones to the right." hasData={!!data?.has_sales} emptyHint={data?.empty ?? "Starts when dishes sell."}>
        <ResponsiveContainer width="100%" height={220}>
          <ScatterChart>
            <XAxis dataKey="x" name="popularity" />
            <YAxis dataKey="y" name="margin %" />
            <Tooltip cursor={{ strokeDasharray: "3 3" }} />
            <Scatter data={quad} fill="#c4b5a8" />
          </ScatterChart>
        </ResponsiveContainer>
      </OwnerChartCard>

      <OwnerChartCard title="Plate profit" caption="Contribution margin in the last 30 days." hasData={(data?.plate_profit?.length ?? 0) > 0} emptyHint={data?.empty ?? "Starts when dishes sell."}>
        <ResponsiveContainer width="100%" height={160}>
          <BarChart data={data?.plate_profit ?? []} layout="vertical" margin={{ left: 8 }}>
            <XAxis type="number" hide />
            <YAxis type="category" dataKey="name" width={88} tick={{ fontSize: 10 }} />
            <Tooltip formatter={(v) => formatKes(Number(v))} />
            <Bar dataKey="kes" fill="#c4b5a8" />
          </BarChart>
        </ResponsiveContainer>
      </OwnerChartCard>

      <OwnerChartCard title="Best sellers" caption="Units sold in the menu engineering window." hasData={(data?.bestsellers?.length ?? 0) > 0} emptyHint={data?.empty ?? "Starts when dishes sell."}>
        <ResponsiveContainer width="100%" height={160}>
          <BarChart data={data?.bestsellers ?? []}>
            <XAxis dataKey="name" tick={{ fontSize: 9 }} interval={0} angle={-25} textAnchor="end" height={50} />
            <YAxis hide />
            <Tooltip />
            <Bar dataKey="plates" fill="#8b7d72" />
          </BarChart>
        </ResponsiveContainer>
      </OwnerChartCard>

      <OwnerChartCard title="Delivery vs dine-in" caption="Paid ticket totals in the last 30 days." hasData={(data?.delivery_vs_dine?.length ?? 0) > 0} emptyHint={data?.empty ?? "Starts when dishes sell."}>
        <ResponsiveContainer width="100%" height={120}>
          <BarChart data={data?.delivery_vs_dine ?? []}>
            <XAxis dataKey="channel" tick={{ fontSize: 10 }} />
            <YAxis hide />
            <Tooltip formatter={(v) => formatKes(Number(v))} />
            <Bar dataKey="kes" fill="#6ee7b7" />
          </BarChart>
        </ResponsiveContainer>
      </OwnerChartCard>

      <ul className="mt-4 space-y-2 text-sm text-zinc-300">
        {(data?.suggestions ?? []).map((s: { title?: string; detail?: string }, i: number) => (
          <li key={i} className="owner-glass-panel px-3 py-2">
            {s.title || s.detail || JSON.stringify(s)}
          </li>
        ))}
      </ul>
    </OwnerShell>
  );
}