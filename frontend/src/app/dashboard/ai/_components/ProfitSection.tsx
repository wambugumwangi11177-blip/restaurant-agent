"use client";

import { TrendingUp } from "lucide-react";
import { formatKES } from "@/lib/format";
import { useAiModule } from "@/lib/useAiModule";
import { NarrativeBlock, type Narrative } from "@/components/ai/NarrativeBlock";
import { ModuleShell } from "@/components/ai/ModuleShell";
import { MiniStat } from "@/components/ai/MiniStat";
import { ExplainButton } from "@/components/ai/ExplainButton";

interface ProfitData {
    summary: { gross_margin_pct: number; food_cost_pct: number; food_cost_status: string; total_gross_profit_30d: number; profit_leaks_found: number; total_leak_amount: number; star_items: number; dog_items: number };
    profit_leaks: { item_name: string; current_margin_pct: number; food_cost_pct: number; monthly_leak_cents: number; severity: string; action: string }[];
    stars: string[];
    dogs: string[];
    narrative?: Narrative;
}

export default function ProfitSection() {
    const { data, loading, error, retry } = useAiModule<ProfitData>("/ai/profit");

    return (
        <ModuleShell icon={TrendingUp} title="Profit Intelligence" explainKey="profit" loading={loading} error={error} onRetry={retry}
            subtitle="Where money leaks out — dishes sold below a healthy margin, and exactly how much each costs you per month.">
            {data && (
                <>
                    <NarrativeBlock n={data.narrative} />
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
                        <MiniStat label="Gross Margin" value={`${data.summary.gross_margin_pct}%`} tone={data.summary.gross_margin_pct >= 55 ? "ok" : "warn"} />
                        <MiniStat label="Food Cost" value={`${data.summary.food_cost_pct}%`} tone={data.summary.food_cost_status === "HEALTHY" ? "ok" : "warn"} />
                        <MiniStat label="Gross Profit (30d)" value={formatKES(data.summary.total_gross_profit_30d)} tone="ok" />
                        <MiniStat label="Leaks Found" value={data.summary.profit_leaks_found} tone={data.summary.profit_leaks_found > 0 ? "warn" : "ok"} />
                    </div>
                    {data.summary.total_leak_amount > 0 && (
                        <div className="mb-4 p-3 rounded-lg bg-emerald-500/5 border border-emerald-500/20">
                            <p className="text-sm text-text">💰 Fixing the flagged items recovers about
                                <span className="text-emerald-400 font-bold"> {formatKES(data.summary.total_leak_amount)}/month</span>.</p>
                        </div>
                    )}
                    {data.profit_leaks && data.profit_leaks.length > 0 && (
                        <div className="space-y-2">
                            {data.profit_leaks.slice(0, 6).map((l, i) => (
                                <div key={i} className="p-3 rounded-lg bg-surface border border-surface-hover text-sm">
                                    <div className="flex items-center justify-between gap-2">
                                        <div className="flex items-center gap-2">
                                            <span className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded ${l.severity === "HIGH" ? "bg-red-500/10 text-red-400" : "bg-amber-500/10 text-amber-400"}`}>{l.severity}</span>
                                            <p className="text-text">{l.item_name}</p>
                                        </div>
                                        <span className="text-red-400 text-xs font-medium whitespace-nowrap">-{formatKES(l.monthly_leak_cents)}/mo</span>
                                    </div>
                                    <p className="text-xs text-text-dim mt-1">Margin {l.current_margin_pct}% · food cost {l.food_cost_pct}%</p>
                                    <p className="text-xs text-[var(--accent)] mt-0.5">💡 {l.action}</p>
                                    <ExplainButton item={l} label={`Profit leak: ${l.item_name}`} />
                                </div>
                            ))}
                        </div>
                    )}
                </>
            )}
        </ModuleShell>
    );
}
