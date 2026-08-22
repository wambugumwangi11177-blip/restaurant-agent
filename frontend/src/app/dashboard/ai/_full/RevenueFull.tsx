"use client";

import { useAiModule } from "@/lib/useAiModule";
import { StatGrid, DataTable, SectionTitle, money, LoadingBlock } from "./shared";

interface ForecastRow { date: string; day: string; predicted_revenue: number; confidence_low: number; confidence_high: number; confidence_pct: number }
interface RevenueData {
    trends: { total_revenue?: number; total_orders?: number; avg_daily_revenue?: number; avg_order_value?: number; week_over_week_growth?: number; month_over_month_growth?: number };
    forecast: ForecastRow[];
    hourly_pattern?: Record<string, unknown>[];
    weekly_pattern?: Record<string, unknown>[];
    revenue_by_type?: Record<string, unknown>[];
    revenue_by_category?: Record<string, unknown>[];
    check_analysis?: Record<string, unknown>;
    spending_segments?: Record<string, unknown>[];
    anomalies?: Record<string, unknown>[];
}

export default function RevenueFull() {
    const { data, loading, error, retry } = useAiModule<RevenueData>("/ai/revenue-forecast");
    if (loading) return <LoadingBlock />;
    if (error) return <div className="flex items-center gap-3"><p className="text-text-dim text-sm">{error}</p><button onClick={retry} className="px-3 py-1.5 rounded-lg bg-[var(--accent)] text-bg text-sm font-semibold">Retry</button></div>;
    if (!data) return null;
    const t = data.trends ?? {};
    const autoTable = (rows: Record<string, unknown>[] | undefined, title: string, maxCols = 7) => {
        if (!rows?.length) return null;
        return (
            <>
                <SectionTitle>{title} ({rows.length})</SectionTitle>
                <DataTable
                    columns={Object.keys(rows[0]).slice(0, maxCols).map(k => ({ key: k, label: k.replace(/_/g, " ") }))}
                    rows={rows } />
            </>
        );
    };
    return (
        <div>
            <StatGrid stats={[
                { label: "Total Revenue (30d)", value: money(t.total_revenue) },
                { label: "Avg / Day", value: money(t.avg_daily_revenue) },
                { label: "WoW Growth", value: `${(t.week_over_week_growth ?? 0) >= 0 ? "+" : ""}${t.week_over_week_growth ?? 0}%`, tone: (t.week_over_week_growth ?? 0) >= 0 ? "ok" : "warn" },
                { label: "MoM Growth", value: `${(t.month_over_month_growth ?? 0) >= 0 ? "+" : ""}${t.month_over_month_growth ?? 0}%`, tone: (t.month_over_month_growth ?? 0) >= 0 ? "ok" : "warn" },
            ]} />
            <SectionTitle>Forecast — every projected day</SectionTitle>
            <DataTable
                columns={[
                    { key: "date", label: "Date" },
                    { key: "day", label: "Day" },
                    { key: "predicted_revenue", label: "Predicted", render: r => <span className="font-semibold">{money(r.predicted_revenue as number)}</span> },
                    { key: "confidence_low", label: "Low", render: r => money(r.confidence_low as number) },
                    { key: "confidence_high", label: "High", render: r => money(r.confidence_high as number) },
                    { key: "confidence_pct", label: "Conf.", render: r => `${r.confidence_pct}%` },
                ]}
                rows={(data.forecast ?? []) }
                empty="Not enough history to forecast." />
            {autoTable(data.hourly_pattern, "Hourly pattern")}
            {autoTable(data.weekly_pattern, "Weekly pattern")}
            {autoTable(data.revenue_by_type, "Revenue by order type")}
            {autoTable(data.revenue_by_category, "Revenue by category")}
            {autoTable(data.spending_segments, "Customer spending segments")}
            {autoTable(data.anomalies, "Anomalies")}
        </div>
    );
}
