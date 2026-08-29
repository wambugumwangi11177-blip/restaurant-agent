"use client";

import { useAiModule } from "@/lib/useAiModule";
import { StatGrid, DataTable, SectionTitle, LoadingBlock } from "./shared";

interface Supplier { id: number; name: string; contact_phone?: string; reliability_score: number; reliability_label: string; total_orders: number; delivered_on_time: number; delivered_late: number; pending_orders?: number; avg_lead_days: number; promised_lead_days?: number; lead_time_variance?: number; cost_trend_pct?: number }
interface SupplyData {
    summary: { total_suppliers?: number; avg_reliability?: number; at_risk?: number; overdue_orders?: number };
    suppliers: Supplier[];
    overdue_orders: Record<string, unknown>[];
    recommendations: { message?: string; action?: string }[];
}

export default function SuppliersFull() {
    const { data, loading, error, retry } = useAiModule<SupplyData>("/ai/supply-chain");
    if (loading) return <LoadingBlock />;
    if (error) return <div className="flex items-center gap-3"><p className="text-text-dim text-sm">{error}</p><button onClick={retry} className="px-3 py-1.5 rounded-lg bg-[var(--accent)] text-bg text-sm font-semibold">Retry</button></div>;
    if (!data) return null;
    const s = data.summary ?? {};
    return (
        <div>
            <StatGrid stats={[
                { label: "Suppliers", value: String(s.total_suppliers ?? data.suppliers.length) },
                { label: "Avg Reliability", value: `${s.avg_reliability ?? 0}%`, tone: (s.avg_reliability ?? 0) >= 90 ? "ok" : "warn" },
                { label: "At Risk", value: String(s.at_risk ?? 0), tone: (s.at_risk ?? 0) > 0 ? "warn" : "ok" },
                { label: "Overdue Orders", value: String(s.overdue_orders ?? data.overdue_orders.length), tone: (data.overdue_orders?.length ?? 0) > 0 ? "warn" : "ok" },
            ]} />
            <SectionTitle>Every supplier</SectionTitle>
            <DataTable
                columns={[
                    { key: "name", label: "Supplier" },
                    { key: "reliability_label", label: "Reliability", render: r => <span className={(r.reliability_score as number) >= 90 ? "text-emerald-400" : (r.reliability_score as number) >= 70 ? "text-amber-400" : "text-red-400"}>{String(r.reliability_label)} ({r.reliability_score}%)</span> },
                    { key: "total_orders", label: "Orders" },
                    { key: "delivered_on_time", label: "On time" },
                    { key: "delivered_late", label: "Late" },
                    { key: "pending_orders", label: "Pending" },
                    { key: "avg_lead_days", label: "Avg lead (d)" },
                    { key: "cost_trend_pct", label: "Price trend", render: r => r.cost_trend_pct != null ? `${(r.cost_trend_pct as number) > 0 ? "+" : ""}${r.cost_trend_pct}%` : "—" },
                ]}
                rows={data.suppliers } />
            <SectionTitle>Overdue orders</SectionTitle>
            <DataTable
                columns={Object.keys(data.overdue_orders?.[0] ?? { order: "" }).slice(0, 7).map(k => ({ key: k, label: k.replace(/_/g, " ") }))}
                rows={(data.overdue_orders ?? []) }
                empty="No overdue orders." />
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
