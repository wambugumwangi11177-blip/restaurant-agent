"use client";

import OwnerShell from "@/components/eleven/OwnerShell";
import OwnerChartCard from "@/components/eleven/charts/OwnerChartCard";
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import api from "@/lib/api";
import { formatKes } from "@/lib/formatKes";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
} from "recharts";

type TodayStrip = {
  sales_kes: number;
  cash_expected_kes: number;
  break_even: string | null;
  has_sales: boolean;
  empty?: string;
};

type SalesSeries = {
  points: { day: string; revenue_kes: number }[];
  has_sales: boolean;
  this_week_kes: number;
  last_week_kes: number;
  empty?: string;
};

type Pnl = {
  has_sales: boolean;
  revenue_cents?: number;
  net_cents?: number;
};

export default function ElevenMoneyPage() {
  const pathname = usePathname() ?? "";
  const [today, setToday] = useState<TodayStrip | null>(null);
  const [series, setSeries] = useState<SalesSeries | null>(null);
  const [pnl, setPnl] = useState<Pnl | null>(null);

  useEffect(() => {
    const bust = { headers: { "Cache-Control": "no-cache" }, params: { _: Date.now() } };
    Promise.all([
      api.get("/api/v1/eleven/money/today", bust),
      api.get("/api/v1/eleven/money/series/sales", { ...bust, params: { days: 30, _: Date.now() } }),
      api.get("/api/v1/eleven/money/pnl", bust),
    ]).then(([a, b, c]) => {
      setToday(a.data);
      setSeries(b.data);
      setPnl(c.data);
    }).catch(() => undefined);
  }, [pathname]);

  return (
    <OwnerShell title="Money">
      <form className="owner-premium-stack" onSubmit={(e) => e.preventDefault()}>
        <section className="owner-glass-panel space-y-1 px-4 py-3">
          <p className="text-lg text-zinc-100">
            Today: {today?.has_sales ? formatKes(today.sales_kes) : "—"}
          </p>
          <p className="text-sm text-zinc-400">
            Cash expected at close:{" "}
            {today?.has_sales ? formatKes(today.cash_expected_kes) : today?.empty ?? "Starts when the till connects."}
          </p>
        </section>

        <OwnerChartCard
          title="Sales — last 30 days"
          caption="Each point is paid tickets for that day."
          detailHref={series?.has_sales ? "/eleven/money/sales" : undefined}
          hasData={!!series?.has_sales}
          emptyHint={series?.empty ?? "Starts when the till connects."}
        >
          <ResponsiveContainer width="100%" height={160}>
            <LineChart data={series?.points ?? []}>
              <XAxis dataKey="day" hide />
              <YAxis hide />
              <Tooltip formatter={(v) => formatKes(Number(v))} />
              <Line type="monotone" dataKey="revenue_kes" stroke="#c4b5a8" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </OwnerChartCard>

        <OwnerChartCard
          title="This week vs last"
          caption="Compares the last seven days with the week before."
          hasData={!!series?.has_sales}
          emptyHint="Starts when the till connects."
        >
          <ResponsiveContainer width="100%" height={140}>
            <BarChart
              data={[
                { name: "Last week", kes: series?.last_week_kes ?? 0 },
                { name: "This week", kes: series?.this_week_kes ?? 0 },
              ]}
            >
              <XAxis dataKey="name" tick={{ fill: "#a1a1aa", fontSize: 11 }} />
              <YAxis hide />
              <Tooltip formatter={(v) => formatKes(Number(v))} />
              <Bar dataKey="kes" fill="#8b7d72" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </OwnerChartCard>

        <OwnerChartCard
          title="P&L snapshot (30 days)"
          caption="Sales minus food, bills, and pay."
          detailHref={pnl?.has_sales ? "/eleven/money/pnl" : undefined}
          hasData={!!pnl?.has_sales}
          emptyHint="Starts when the till connects."
        >
          <p className="px-2 text-2xl text-zinc-100">{formatKes((pnl?.net_cents ?? 0) / 100)}</p>
          <p className="px-2 text-xs text-zinc-400">Net after costs</p>
        </OwnerChartCard>

        <p className="text-center text-xs text-zinc-500">
          More charts (forecast, dishes, bills, heatmap) ship in the next batch on this branch.
        </p>
      </form>
    </OwnerShell>
  );
}