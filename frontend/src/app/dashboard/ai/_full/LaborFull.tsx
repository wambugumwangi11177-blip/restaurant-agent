"use client";

import { useAiModule } from "@/lib/useAiModule";
import { StatGrid, DataTable, SectionTitle, money, LoadingBlock } from "./shared";

interface LaborData {
    summary: { total_labor_cost_30d?: number; labor_pct?: number; labor_status?: string; sales_per_hour?: number; overtime_cost_30d?: number };
    daily_breakdown: { date: string; day: string; labor_cost: number; hours: number; revenue: number; labor_pct: number }[];
    staff_productivity: { staff_name: string; hours_worked: number; labor_cost: number; est_revenue_generated: number; cost_pct_of_revenue: number }[];
    recommendations: { priority?: string; message: string; action?: string }[];
}

export default function LaborFull() {
    const { data, loading, error, retry } = useAiModule<LaborData>("/ai/labor");
    if (loading) return <LoadingBlock />;
    if (error) return <div className="flex items-center gap-3"><p className="text-text-dim text-sm">{error}</p><button onClick={retry} className="px-3 py-1.5 rounded-lg bg-[var(--accent)] text-bg text-sm font-semibold">Retry</button></div>;
    if (!data) return null;
    const s = data.summary ?? {};
    return (
        <div>
            <StatGrid stats={[
                { label: "Labor Cost (30d)", value: money(s.total_labor_cost_30d) },
                { label: "Labor %", value: `${s.labor_pct ?? 0}%`, tone: (s.labor_pct ?? 0) > 30 ? "warn" : "ok" },
                { label: "Sales / Hour", value: money(s.sales_per_hour) },
                { label: "Overtime (30d)", value: money(s.overtime_cost_30d), tone: (s.overtime_cost_30d ?? 0) > 0 ? "warn" : "ok" },
            ]} />
            <SectionTitle>Daily labor vs revenue</SectionTitle>
            <DataTable
                columns={[
                    { key: "date", label: "Date" },
                    { key: "day", label: "Day" },
                    { key: "hours", label: "Hours" },
                    { key: "labor_cost", label: "Labor cost", render: r => money(r.labor_cost as number) },
                    { key: "revenue", label: "Revenue", render: r => money(r.revenue as number) },
                    { key: "labor_pct", label: "Labor %", render: r => <span className={(r.labor_pct as number) > 40 ? "text-red-400" : (r.labor_pct as number) > 30 ? "text-amber-400" : "text-emerald-400"}>{r.labor_pct}%</span> },
                ]}
                rows={data.daily_breakdown } />
            <SectionTitle>Staff productivity — everyone</SectionTitle>
            <DataTable
                columns={[
                    { key: "staff_name", label: "Staff" },
                    { key: "hours_worked", label: "Hours" },
                    { key: "labor_cost", label: "Cost", render: r => money(r.labor_cost as number) },
                    { key: "est_revenue_generated", label: "Revenue generated", render: r => money(r.est_revenue_generated as number) },
                    { key: "cost_pct_of_revenue", label: "Cost % of revenue", render: r => `${r.cost_pct_of_revenue}%` },
                ]}
                rows={data.staff_productivity } />
            {(data.recommendations?.length ?? 0) > 0 && (
                <>
                    <SectionTitle>Recommendations</SectionTitle>
                    <div className="space-y-2">
                        {data.recommendations.map((r, i) => (
                            <div key={i} className="p-3 rounded-lg bg-surface border border-surface-hover text-sm">
                                <p className="text-text">{r.message}</p>
                                {r.action && <p className="text-xs text-[var(--accent)] mt-1">💡 {r.action}</p>}
                            </div>
                        ))}
                    </div>
                </>
            )}
        </div>
    );
}
