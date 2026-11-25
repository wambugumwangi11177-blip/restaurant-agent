"use client";

import OwnerShell from "@/components/eleven/OwnerShell";
import OwnerChartCard from "@/components/eleven/charts/OwnerChartCard";
import { useOwnerGet } from "@/hooks/useOwnerV11";
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export default function MoneyBillsPage() {
  const { data } = useOwnerGet<{
    has_sales?: boolean;
    paid?: number;
    due?: number;
    unknown?: number;
    cash_after_bills?: { day: string; after_bills_kes: number }[];
    empty?: string;
  }>("/api/v1/eleven/money/bills", []);

  const series = data?.cash_after_bills ?? [];

  return (
    <OwnerShell title="Bills & cash">
      <div className="owner-premium-stack">
        <section className="owner-glass-panel px-4 py-3 text-sm text-zinc-300">
          <p>
            Paid {data?.paid ?? 0} · due {data?.due ?? 0} · unknown {data?.unknown ?? 0}
          </p>
        </section>
        <OwnerChartCard
          title="Cash after bills (30d trend)"
          caption="Sales minus approved bills — not auto-paid; you still approve each bill."
          hasData={series.length > 0}
          emptyHint={data?.empty ?? "Starts when bills are in Settings."}
        >
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={series}>
              <XAxis dataKey="day" tick={{ fill: "#a1a1aa", fontSize: 10 }} />
              <YAxis hide />
              <Tooltip />
              <Line type="monotone" dataKey="after_bills_kes" stroke="#c4b5a8" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </OwnerChartCard>
      </div>
    </OwnerShell>
  );
}