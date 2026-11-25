"use client";

import OwnerShell from "@/components/eleven/OwnerShell";
import { ForecastBlock, PieBlock, SalesLineBlock, WaterfallBlock, WeekBarsBlock } from "@/components/eleven/v11/ChartBlocks";
import ExplainedCard from "@/components/eleven/charts/ExplainedCard";
import { fmtK } from "@/lib/chartFormat";
import { useOwnerGet } from "@/hooks/useOwnerV11";
import { formatKes } from "@/lib/formatKes";
import {
  Bar,
  Cell,
  BarChart,
  ComposedChart,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import HeatmapGrid from "@/components/eleven/charts/HeatmapGrid";

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
  const { data: month3 } = useOwnerGet<{ bars?: { month: string; kes: number; partial?: boolean }[]; has_sales?: boolean; average_kes?: number; empty?: string }>("/api/v1/eleven/money/three-month", []);
  const { data: bills } = useOwnerGet<{ cash_after_bills?: { day: string; after_bills_kes: number }[] }>("/api/v1/eleven/money/bills", []);
  const { data: suppliers } = useOwnerGet<{ lines?: { name: string; trend: { kes_per_unit: number }[] }[] }>("/api/v1/eleven/money/supplier-prices", []);
  const { data: dishSum } = useOwnerGet<{ quadrant?: { name?: string; x: number; y: number }[]; has_sales?: boolean }>("/api/v1/eleven/money/dishes/summary", []);

  const foodPts = (food as { points?: { week: string; pct: number; over_target?: boolean }[] })?.points ?? [];
  const heatCells = (heat as { cells?: { dow: number; hour: number; kes: number }[] })?.cells ?? [];

  const foodAvg = foodPts.length ? foodPts.reduce((a, p) => a + (p.pct ?? 0), 0) / foodPts.length : 0;
  const foodLast = foodPts.length ? foodPts[foodPts.length - 1].pct : null;
  const foodOver = foodPts.filter((p) => p.over_target).length;
  const afterBills = bills?.cash_after_bills ?? [];
  const lowest = afterBills.reduce<{ day: string; after_bills_kes: number } | null>((m, p) => (m == null || p.after_bills_kes < m.after_bills_kes ? p : m), null);
  const goalPct = goals?.progress_pct ?? null;

  return (
    <OwnerShell title="Money">
      <div className="owner-premium-stack">
        <section className="owner-glass-panel space-y-1 px-4 py-3">
          <p className="text-xs uppercase tracking-wide text-zinc-400">Today</p>
          <p className="text-xl text-zinc-50">{today?.has_sales ? formatKes(today.sales_kes) : "—"} sold</p>
          <p className="text-sm text-zinc-300">
            Cash you should have at close: {today?.has_sales ? formatKes(today.cash_expected_kes) : today?.empty}
            {(today as { cash_expected_note?: string })?.cash_expected_note ? ` — ${(today as { cash_expected_note?: string }).cash_expected_note}` : ""}
          </p>
          <p className="text-[11px] uppercase tracking-wide text-zinc-500">Live · from your till</p>
        </section>

        <SectionHead q="Is money coming in?" hint="Sales over time, and how this week compares." />
        <SalesLineBlock data={series as never} />
        <WeekBarsBlock data={series as never} />
        <ExplainedCard
          title="Last 3 months"
          headline={month3?.average_kes ? `About ${formatKes(month3.average_kes)} a month` : undefined}
          what="One bar per calendar month. The dashed green line is the average of the bars. A bar marked partial is a month still running."
          hasData={!!month3?.has_sales}
          emptyHint={month3?.empty ?? "Starts when the till connects."}
        >
          <ResponsiveContainer width="100%" height={160}>
            <ComposedChart data={month3?.bars ?? []} margin={{ top: 16, right: 8, left: 0, bottom: 0 }}>
              <XAxis dataKey="month" tick={{ fill: "#a1a1aa", fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis hide domain={[0, "dataMax"]} />
              <Tooltip formatter={(v) => formatKes(Number(v))} />
              <Bar dataKey="kes" fill="#c4b5a8" radius={[4, 4, 0, 0]} label={{ position: "top", fill: "#e4e4e7", fontSize: 10, formatter: (v: unknown) => fmtK(Number(v)) }} />
              {month3?.average_kes ? <ReferenceLine y={month3.average_kes} stroke="#6ee7b7" strokeDasharray="4 4" /> : null}
            </ComposedChart>
          </ResponsiveContainer>
        </ExplainedCard>
        <ExplainedCard
          title="Busiest hours"
          what="Each square is an hour on a weekday. Darker means more sales. Use it to staff for the hours that earn."
          detailHref={heatCells.length ? "/eleven/money/sales" : undefined}
          hasData={heatCells.length > 0}
          emptyHint="Starts when the till connects."
        >
          <HeatmapGrid cells={heatCells} />
        </ExplainedCard>

        <SectionHead q="Where does it go?" hint="From each sale down to what you keep." />
        <WaterfallBlock data={waterfall as never} />
        <PieBlock
          title="Where the money went · 30 days"
          caption="Your sales split into ingredients, running costs, wages and what is left."
          slices={where?.slices ?? []}
          has={!!where?.has_sales}
          empty={where?.empty ?? "Starts when the till connects."}
        />
        <ExplainedCard
          title="Ingredients as a share of sales"
          headline={foodLast != null ? `KES ${foodLast} of every KES 100 goes on ingredients` : undefined}
          sub={foodPts.length ? `Average ${Math.round(foodAvg * 10) / 10}% over ${foodPts.length} weeks` : undefined}
          verdict={foodOver > 0 ? { tone: "watch", text: `${foodOver} of ${foodPts.length} weeks were above your target.` } : foodPts.length ? { tone: "good", text: "Every week is within your target." } : undefined}
          what="One bar per week. Red bars are weeks above the food-cost target you set in Settings. A bar drifting up week after week is the earliest sign ingredients are eating the profit."
          why="Food cost % = ingredient cost ÷ sales × 100. Needs recipes and sales."
          freshness="As entered · from recipes and your till"
          hasData={foodPts.some((p) => p.pct != null)}
          emptyHint="Starts when recipes and sales exist."
        >
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={foodPts} margin={{ top: 16, right: 8, left: 0, bottom: 0 }}>
              <XAxis dataKey="week" tick={{ fill: "#a1a1aa", fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis hide domain={[0, "dataMax"]} />
              <Tooltip formatter={(v) => `${v}%`} />
              <Bar dataKey="pct" radius={[4, 4, 0, 0]} label={{ position: "top", fill: "#e4e4e7", fontSize: 10, formatter: (v: unknown) => `${v}%` }}>
                {foodPts.map((p, i) => (
                  <Cell key={i} fill={p.over_target ? "#f87171" : "#8b7d72"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ExplainedCard>
        <PieBlock
          title="How customers paid · 30 days"
          caption="Cash goes in the drawer today; M-Pesa and card reach the business separately. The cash slice is what your drawer should hold."
          slices={pay?.slices ?? []}
          has={!!pay?.has_sales}
          empty={pay?.empty ?? "Starts when payment type is recorded."}
        />
        <ExplainedCard
          title="Supplier prices"
          what="Unit price on the last invoices for your first supplier line. A line climbing is a supplier getting dearer. LEVIII only suggests; you decide."
          detailHref="/eleven/money/supplier-prices"
          hasData={(suppliers?.lines?.length ?? 0) > 0}
          emptyHint="Starts when supplier invoices are entered."
        >
          <ResponsiveContainer width="100%" height={140}>
            <LineChart data={suppliers?.lines?.[0]?.trend ?? []} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <XAxis dataKey="at" hide />
              <YAxis width={36} tickFormatter={fmtK} tick={{ fill: "#a1a1aa", fontSize: 10 }} axisLine={false} tickLine={false} tickCount={3} domain={["auto", "auto"]} />
              <Tooltip formatter={(v) => formatKes(Number(v))} />
              <Line type="monotone" dataKey="kes_per_unit" stroke="#c4b5a8" strokeWidth={2} dot />
            </LineChart>
          </ResponsiveContainer>
        </ExplainedCard>

        <SectionHead q="What is coming?" hint="Next week's sales, bills, and your monthly goal." />
        <ForecastBlock data={forecast as never} />
        <ExplainedCard
          title="Bills and cash after bills"
          headline={lowest ? `Lowest point: ${formatKes(lowest.after_bills_kes)}` : undefined}
          verdict={lowest ? (lowest.after_bills_kes < 0 ? { tone: "bad", text: "Bills will outrun cash. Act before that day." } : { tone: "good", text: "Cash stays above zero." }) : undefined}
          what="The line is the cash you expect to have each day after approved bills are paid. Where it drops below zero you will be short."
          detailHref="/eleven/money/bills"
          hasData={afterBills.length > 0}
          emptyHint="Add bills to see this."
        >
          <ResponsiveContainer width="100%" height={150}>
            <LineChart data={afterBills} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <XAxis dataKey="day" tick={{ fill: "#a1a1aa", fontSize: 9 }} axisLine={false} tickLine={false} />
              <YAxis width={40} tickFormatter={fmtK} tick={{ fill: "#a1a1aa", fontSize: 10 }} axisLine={false} tickLine={false} tickCount={4} />
              <ReferenceLine y={0} stroke="#f87171" strokeDasharray="4 4" />
              <Tooltip formatter={(v) => formatKes(Number(v))} />
              <Line type="monotone" dataKey="after_bills_kes" stroke="#c4b5a8" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </ExplainedCard>
        <ExplainedCard
          title="Monthly sales goal"
          headline={goalPct != null ? `${goalPct}% of ${formatKes(goals?.target_kes)}` : undefined}
          verdict={goalPct != null ? (goalPct >= 100 ? { tone: "good", text: "Goal reached." } : { tone: "neutral", text: `${formatKes(Math.max((goals?.target_kes ?? 0) * (1 - goalPct / 100), 0))} still to go.` }) : undefined}
          what="How far this month's sales have got towards the target you set."
          detailHref={goals?.has_sales ? "/eleven/money/pnl" : undefined}
          hasData={!!goals?.target_kes}
          emptyHint={goals?.empty ?? "Set targets in Settings."}
        >
          <div className="h-3 w-full overflow-hidden rounded-full bg-zinc-700/60" role="progressbar" aria-valuenow={goalPct ?? 0} aria-valuemin={0} aria-valuemax={100}>
            <div className="h-full rounded-full bg-emerald-400" style={{ width: `${Math.min(goalPct ?? 0, 100)}%` }} />
          </div>
        </ExplainedCard>

        <SectionHead q="Which dishes earn?" hint="Popular against profitable." />
        <ExplainedCard
          title="Your dishes"
          what="Each dot is a dish. Further right sells more; higher keeps more per plate. Top-right dishes are your best; bottom-left are candidates to rework or remove."
          detailHref="/eleven/money/dishes"
          hasData={!!dishSum?.has_sales}
          emptyHint="Opens when dishes sell."
        >
          <ResponsiveContainer width="100%" height={170}>
            <ScatterChart margin={{ top: 8, right: 12, left: 0, bottom: 16 }}>
              <XAxis dataKey="x" name="Popularity" type="number" tick={{ fill: "#a1a1aa", fontSize: 10 }} axisLine={false} tickLine={false} label={{ value: "Sells more →", position: "insideBottom", offset: -8, fill: "#a1a1aa", fontSize: 10 }} />
              <YAxis dataKey="y" name="Margin" type="number" width={36} tick={{ fill: "#a1a1aa", fontSize: 10 }} axisLine={false} tickLine={false} label={{ value: "Keeps more ↑", angle: -90, position: "insideLeft", fill: "#a1a1aa", fontSize: 10 }} />
              <Tooltip cursor={{ strokeDasharray: "3 3" }} />
              <Scatter data={dishSum?.quadrant ?? []} fill="#c4b5a8" />
            </ScatterChart>
          </ResponsiveContainer>
        </ExplainedCard>
      </div>
    </OwnerShell>
  );
}

function SectionHead({ q, hint }: { q: string; hint: string }) {
  return (
    <header className="px-1 pt-3">
      <h2 className="text-base text-zinc-50">{q}</h2>
      <p className="text-xs text-zinc-400">{hint}</p>
    </header>
  );
}
