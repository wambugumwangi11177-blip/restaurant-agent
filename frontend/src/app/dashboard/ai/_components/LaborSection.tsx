"use client";

import { Activity } from "lucide-react";
import { formatKES } from "@/lib/format";
import { useAiModule } from "@/lib/useAiModule";
import { MiniStat } from "@/components/ai/MiniStat";
import { ModuleShell } from "@/components/ai/ModuleShell";

interface LaborData {
    summary: { total_labor_cost_30d: number; labor_pct: number; labor_status: string; sales_per_hour: number; overtime_cost_30d: number };
    recommendations: { priority: string; message: string; action: string }[];
}

export default function LaborSection() {
    const { data, loading, error, retry } = useAiModule<LaborData>("/ai/labor");

    return (
        <ModuleShell icon={Activity} title="Labor Optimization" explainKey="labor" loading={loading} error={error} onRetry={retry}>
            {data && (
                <>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
                        <MiniStat label="Labor Cost (30d)" value={formatKES(data.summary.total_labor_cost_30d)} />
                        <MiniStat label="Labor %" value={`${data.summary.labor_pct}%`} tone={data.summary.labor_status === "HIGH" ? "warn" : "ok"} />
                        <MiniStat label="Sales/Hour" value={formatKES(data.summary.sales_per_hour)} />
                        <MiniStat label="Overtime Cost" value={formatKES(data.summary.overtime_cost_30d)} />
                    </div>
                    {data.recommendations.length === 0 ? (
                        <p className="text-text-dim text-sm">Staffing looks well balanced.</p>
                    ) : (
                        <div className="space-y-2">
                            {data.recommendations.slice(0, 4).map((r, i) => (
                                <div key={i} className="p-3 rounded-lg bg-surface border border-surface-hover text-sm">
                                    <p className="text-text">{r.message}</p>
                                    {r.action && <p className="text-xs text-[var(--accent)] mt-1">💡 {r.action}</p>}
                                </div>
                            ))}
                        </div>
                    )}
                </>
            )}
        </ModuleShell>
    );
}
