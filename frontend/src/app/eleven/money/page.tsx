"use client";

import Link from "next/link";
import OwnerShell from "@/components/eleven/OwnerShell";
import { ForecastBlock, PieBlock, SalesLineBlock, WaterfallBlock, WeekBarsBlock } from "@/components/eleven/v11/ChartBlocks";
import OwnerChartCard from "@/components/eleven/charts/OwnerChartCard";
import { useOwnerGet } from "@/hooks/useOwnerV11";
import { formatKes } from "@/lib/formatKes";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export default function ElevenMoneyPage() {
  const { data: today } = useOwnerGet<{ sales_kes: number; cash_expected_kes: number; has_sales: boolean; empty?: string }>("/api/v1/eleven/money/today", []);
  const { data: series } = useOwnerGet("/api/v1/eleven/money/series/sales?days=30", []);
  const { data: forecast } = useOwnerGet("/api/v1/eleven/money/forecast", []);
  const { data: waterfall } = useOwnerGet("/api/v1/eleven/money/waterfall", []);
  const { data: where } = useOwnerGet<{ has_sales?: boolean; slices?: { name: string; kes: number }[]; empty?: string }>("/api/v1/eleven/money/where", []);
  const { data: food } = useOwnerGet<{ points?: { week: string; pct: number }[] }>("/api/v1/eleven/money/food-cost-series", []);
  const { data: pay } = useOwnerGet<{ has_sales?: boolean; slices?: { name: string; kes: number }[]; empty?: string }>("/api/v1/eleven/money/payments", []);
  const { data: goals } = useOwnerGet<{ has_sales?: boolean; progress_pct?: number; target_kes?: number; empty?: string }>("/api/v1/eleven/money/goals", []);
  const { data: heat } = useOwnerGet("/api/v1/eleven/money/heatmap", []);
  const { data: month3 } = useOwnerGet<{ bars?: { month: string; kes: number }[]; has_sales?: boolean; empty?: string }>("/api/v1/eleven/money/three-month", []);

  const foodPts = (food as { points?: { week: string; pct: number; over_target?: boolean }[] })?.points ?? [];
  const heatCells = (heat as { cells?: { dow: number; hour: number; kes: number }[] })?.cells ?? [];

  return (
    <OwnerShell title="Money">
      <div className="owner-premium-stack">
        <section className="owner-glass-panel px-4 py-3">
          <p className="text-lg text-zinc-100">Today: {today?.has_sales ? formatKes(today.sales_kes) : "—"}</p>
          <p className="text-sm text-zinc-400">
            Cash expected at close: {today?.has_sales ? formatKes(today.cash_expected_kes) : today?.empty}
          </p>
        </section>

        <SalesLineBlock data={series as never} />
        <WeekBarsBlock data={series as never} />
        <ForecastBlock data={forecast as never} />
        <WaterfallBlock data={waterfall as never} />

        <PieBlock
          title="Where the money went (30d)"
          caption="Food, bills, pay, and what is left."
          slices={where?.slices ?? []}
          has={!!where?.has_sales}
          empty={where?.empty ?? "Starts when the till connects."}
        />

        <OwnerChartCard
          title="Food cost % vs target"
          caption="Red weeks are above your target in Settings."
          hasData={foodPts.some((p) => p.pct != null)}
          emptyHint="Starts when recipes and sales exist."
        >
          <ResponsiveContainer width="100%" height={140}>
            <BarChart data={foodPts}>
              <XAxis dataKey="week" tick={{ fill: "#a1a1aa", fontSize: 10 }} />
              <YAxis hide />
              <Tooltip />
              <Bar dataKey="pct" fill="#8b7d72" />
            </BarChart>
          </ResponsiveContainer>
        </OwnerChartCard>

        <PieBlock
          title="Cash vs M-Pesa"
          caption="Expected drawer is cash sales in the last 30 days."
          slices={pay?.slices ?? []}
          has={!!pay?.has_sales}
          empty={pay?.empty ?? "Starts when payment type is recorded."}
        />

        <OwnerChartCard
          title="Monthly sales goal"
          caption="Progress against the target you set."
          detailHref={goals?.has_sales ? "/eleven/money/pnl" : undefined}
          hasData={!!goals?.target_kes}
          emptyHint={goals?.empty ?? "Set targets in Settings."}
        >
          <p className="text-2xl text-zinc-100">{goals?.progress_pct != null ? `${goals.progress_pct}%` : "—"}</p>
        </OwnerChartCard>

        <OwnerChartCard
          title="Hour × day heatmap"
          caption="Busier cells are darker — tap through on the sales detail page."
          detailHref={heatCells.length ? "/eleven/money/sales" : undefined}
          hasData={heatCells.length > 0}
          emptyHint="Starts when the till connects."
        >
          <p className="text-sm text-zinc-400">{heatCells.length} busy slots recorded</p>
        </OwnerChartCard>

        <OwnerChartCard
          title="Bills & cash after bills"
          caption="30-day line after approved bills."
          detailHref="/eleven/money/bills"
          hasData
          emptyHint="See bills detail."
        >
          <Link href="/eleven/money/bills" className="text-sm text-white underline">
            Open bills detail
          </Link>
        </OwnerChartCard>

        <OwnerChartCard
          title="Supplier price trends"
          caption="Last invoice unit prices — suggest-only; humans approve."
          detailHref="/eleven/money/supplier-prices"
          hasData
          emptyHint="See supplier trends."
        >
          <Link href="/eleven/money/supplier-prices" className="text-sm text-white underline">
            Open supplier trends
          </Link>
        </OwnerChartCard>

        <OwnerChartCard title="Last 3 months" caption="Bars are calendar months; line is the average." hasData={!!month3?.has_sales} emptyHint={month3?.empty ?? "Starts when the till connects."}>
          <ResponsiveContainer width="100%" height={140}>
            <BarChart data={month3?.bars ?? []}>
              <XAxis dataKey="month" tick={{ fill: "#a1a1aa", fontSize: 10 }} />
              <YAxis hide />
              <Tooltip formatter={(v) => formatKes(Number(v))} />
              <Bar dataKey="kes" fill="#c4b5a8" />
            </BarChart>
          </ResponsiveContainer>
        </OwnerChartCard>

        <OwnerChartCard title="Dishes" caption="Popularity vs profit, Pareto, and price ideas." detailHref="/eleven/money/dishes" hasData={!!series?.has_sales} emptyHint="Opens when dishes sell.">
          <p className="text-sm text-zinc-300">Open the dishes hub →</p>
        </OwnerChartCard>
      </div>
    </OwnerShell>
  );
}