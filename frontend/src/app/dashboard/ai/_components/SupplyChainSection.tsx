"use client";

import { Truck } from "lucide-react";
import { useAiModule } from "@/lib/useAiModule";
import { ModuleShell } from "@/components/ai/ModuleShell";
import { MiniStat } from "@/components/ai/MiniStat";

interface Supplier {
    id: number; name: string; reliability_score: number; reliability_label: string;
    delivered_on_time: number; delivered_late: number; pending_orders: number;
    avg_lead_days: number; lead_time_variance: number; cost_trend_pct: number; cost_trend_label: string; at_risk: boolean;
}

interface SupplyData {
    summary: { total_suppliers: number; overdue_orders: number; at_risk_suppliers: number; avg_reliability_pct: number };
    suppliers: Supplier[];
    overdue_orders: { supplier_name?: string; expected_at?: string }[];
    recommendations: { type?: string; priority?: string; message: string }[];
}

export default function SupplyChainSection() {
    const { data, loading, error, retry } = useAiModule<SupplyData>("/ai/supply-chain");

    return (
        <ModuleShell icon={Truck} title="Supplier Intelligence" explainKey="supply" loading={loading} error={error} onRetry={retry}
            fullHref="/dashboard/ai/suppliers"
            subtitle="Which suppliers deliver on time, whose prices are creeping up, and which orders are overdue.">
            {data && (
                <>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
                        <MiniStat label="Suppliers" value={data.summary.total_suppliers} />
                        <MiniStat label="Avg reliability" value={`${data.summary.avg_reliability_pct}%`} tone={data.summary.avg_reliability_pct >= 85 ? "ok" : "warn"} />
                        <MiniStat label="At risk" value={data.summary.at_risk_suppliers} tone={data.summary.at_risk_suppliers > 0 ? "warn" : "ok"} />
                        <MiniStat label="Overdue orders" value={data.summary.overdue_orders} tone={data.summary.overdue_orders > 0 ? "warn" : "ok"} />
                    </div>
                    {data.suppliers.length === 0 ? (
                        <p className="text-text-dim text-sm">No suppliers set up yet — add suppliers and purchase orders and this fills in.</p>
                    ) : (
                        <div className="space-y-2">
                            {data.suppliers.slice(0, 6).map((s) => (
                                <div key={s.id} className="p-3 rounded-lg bg-surface border border-surface-hover text-sm">
                                    <div className="flex items-center justify-between gap-2">
                                        <div className="flex items-center gap-2 flex-wrap">
                                            <p className="text-text">{s.name}</p>
                                            <span className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded ${s.reliability_label === "EXCELLENT" ? "bg-emerald-500/10 text-emerald-400" : s.reliability_label === "GOOD" ? "bg-info/10 text-[#60a5fa]" : "bg-red-500/10 text-red-400"}`}>{s.reliability_label}</span>
                                        </div>
                                        <span className={`text-xs font-medium whitespace-nowrap ${s.reliability_score >= 85 ? "text-emerald-400" : "text-red-400"}`}>{s.reliability_score}% on time</span>
                                    </div>
                                    <p className="text-xs text-text-dim mt-1">
                                        {s.delivered_on_time} on time · {s.delivered_late} late
                                        {s.pending_orders > 0 ? ` · ${s.pending_orders} pending` : ""}
                                        {" · "}avg lead {s.avg_lead_days}d
                                        {s.cost_trend_label !== "stable" ? ` · prices ${s.cost_trend_label} ${Math.abs(s.cost_trend_pct)}%` : ""}
                                    </p>
                                </div>
                            ))}
                        </div>
                    )}
                    {data.recommendations && data.recommendations.length > 0 && (
                        <div className="mt-3 space-y-2">
                            {data.recommendations.slice(0, 4).map((r, i) => (
                                <div key={i} className="p-3 rounded-lg bg-surface border border-surface-hover text-sm">
                                    <p className="text-text">{r.message}</p>
                                </div>
                            ))}
                        </div>
                    )}
                </>
            )}
        </ModuleShell>
    );
}
