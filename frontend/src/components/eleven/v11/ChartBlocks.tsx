"use client";

import Link from "next/link";
import {
  Bar,
  BarChart,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import OwnerChartCard from "@/components/eleven/charts/OwnerChartCard";
import { formatKes } from "@/lib/formatKes";

const COLORS = ["#c4b5a8", "#8b7d72", "#6b5e55", "#a89a8f"];

export function SalesLineBlock({ data }: { data: { points?: { day: string; revenue_kes: number }[]; has_sales?: boolean; empty?: string } | null }) {
  const has = !!data?.has_sales;
  return (
    <OwnerChartCard title="Sales — last 30 days" caption="Each point is paid tickets for that day." detailHref={has ? "/eleven/money/sales" : undefined} hasData={has} emptyHint={data?.empty ?? "Starts when the till connects."}>
      <ResponsiveContainer width="100%" height={150}>
        <LineChart data={data?.points ?? []}>
          <XAxis dataKey="day" hide />
          <YAxis hide />
          <Tooltip formatter={(v) => formatKes(Number(v))} />
          <Line type="monotone" dataKey="revenue_kes" stroke="#c4b5a8" strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </OwnerChartCard>
  );
}

export function WeekBarsBlock({ data }: { data: { has_sales?: boolean; this_week_kes?: number; last_week_kes?: number; empty?: string } | null }) {
  const has = !!data?.has_sales;
  return (
    <OwnerChartCard title="This week vs last" caption="Compares the last seven days with the week before." hasData={has} emptyHint={data?.empty ?? "Starts when the till connects."}>
      <ResponsiveContainer width="100%" height={130}>
        <BarChart data={[{ name: "Last week", kes: data?.last_week_kes ?? 0 }, { name: "This week", kes: data?.this_week_kes ?? 0 }]}>
          <XAxis dataKey="name" tick={{ fill: "#a1a1aa", fontSize: 11 }} />
          <YAxis hide />
          <Tooltip formatter={(v) => formatKes(Number(v))} />
          <Bar dataKey="kes" fill="#8b7d72" radius={[6, 6, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </OwnerChartCard>
  );
}

export function ForecastBlock({ data }: { data: { points?: { day: string; low_kes: number; high_kes: number; mid_kes: number }[]; has_sales?: boolean; empty?: string } | null }) {
  const has = !!data?.has_sales;
  return (
    <OwnerChartCard title="Next 7 days (range)" caption="Band is low to high sales based on your recent pattern." hasData={has} emptyHint={data?.empty ?? "Need about a week of sales first."}>
      <ResponsiveContainer width="100%" height={150}>
        <BarChart data={data?.points ?? []}>
          <XAxis dataKey="day" hide />
          <YAxis hide />
          <Tooltip />
          <Bar dataKey="low_kes" stackId="a" fill="#4b5563" />
          <Bar dataKey="mid_kes" stackId="a" fill="#c4b5a8" />
        </BarChart>
      </ResponsiveContainer>
    </OwnerChartCard>
  );
}

export function WaterfallBlock({ data }: { data: { steps?: { label: string; kes: number }[]; has_sales?: boolean; empty?: string } | null }) {
  const has = !!data?.has_sales;
  return (
    <OwnerChartCard title="P&L waterfall (month to date)" caption="How sales flow to net after food, bills, and pay." detailHref={has ? "/eleven/money/pnl" : undefined} hasData={has} emptyHint={data?.empty ?? "Starts when the till connects."}>
      <ResponsiveContainer width="100%" height={160}>
        <BarChart data={data?.steps ?? []}>
          <XAxis dataKey="label" tick={{ fill: "#a1a1aa", fontSize: 10 }} interval={0} angle={-20} textAnchor="end" height={50} />
          <YAxis hide />
          <Tooltip formatter={(v) => formatKes(Number(v))} />
          <Bar dataKey="kes" fill="#8b7d72" />
        </BarChart>
      </ResponsiveContainer>
    </OwnerChartCard>
  );
}

export function PieBlock({ title, caption, slices, has, empty, href }: { title: string; caption: string; slices: { name: string; kes: number }[]; has: boolean; empty: string; href?: string }) {
  const body = (
    <ResponsiveContainer width="100%" height={150}>
      <PieChart>
        <Pie data={slices} dataKey="kes" nameKey="name" innerRadius={40} outerRadius={60}>
          {slices.map((_, i) => (
            <Cell key={i} fill={COLORS[i % COLORS.length]} />
          ))}
        </Pie>
        <Tooltip formatter={(v) => formatKes(Number(v))} />
      </PieChart>
    </ResponsiveContainer>
  );
  if (href && has) {
    return (
      <Link href={href}>
        <OwnerChartCard title={title} caption={caption} hasData={has} emptyHint={empty}>
          {body}
        </OwnerChartCard>
      </Link>
    );
  }
  return (
    <OwnerChartCard title={title} caption={caption} hasData={has} emptyHint={empty}>
      {body}
    </OwnerChartCard>
  );
}