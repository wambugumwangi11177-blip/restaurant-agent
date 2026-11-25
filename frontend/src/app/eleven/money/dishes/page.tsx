"use client";

import OwnerShell from "@/components/eleven/OwnerShell";
import OwnerChartCard from "@/components/eleven/charts/OwnerChartCard";
import { useOwnerGet } from "@/hooks/useOwnerV11";
import { ScatterChart, Scatter, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";

export default function DishesMoneyPage() {
  const { data } = useOwnerGet<{
    has_sales?: boolean;
    empty?: string;
    quadrant?: { x: number; y: number; name?: string }[];
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