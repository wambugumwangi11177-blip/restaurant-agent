"use client";

import { Brain } from "lucide-react";
import { useAiModule } from "@/lib/useAiModule";
import { NarrativeBlock, type Narrative } from "@/components/ai/NarrativeBlock";
import { ModuleShell } from "@/components/ai/ModuleShell";
import { MENU_CLASS } from "./constants";

interface MenuData {
    summary: { total_items: number; stars: number; plowhorses: number; puzzles: number; dogs: number; avg_food_cost_pct: number; menu_optimization_score?: number };
    category_performance: { category: string; revenue_share_pct: number; avg_margin_pct: number; item_count: number }[];
    recommendations: { item: string; action: string; reason: string; priority: string; impact: string }[];
    narrative?: Narrative;
}

export default function MenuEngineeringSection() {
    const { data, loading, error, retry } = useAiModule<MenuData>("/ai/menu-engineering");

    return (
        <ModuleShell icon={Brain} title="Menu Engineering" explainKey="menu" loading={loading} error={error} onRetry={retry}
            fullHref="/dashboard/ai/menu"
            subtitle="Classifies every dish by popularity × profit so you know what to promote, reprice, or cut.">
            {data && (
                <>
                    <NarrativeBlock n={data.narrative} />
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3">
                        {([["Stars", data.summary.stars], ["Plowhorses", data.summary.plowhorses],
                          ["Puzzles", data.summary.puzzles], ["Dogs", data.summary.dogs]] as const).map(([k, v]) => (
                            <div key={k} className="rounded-lg bg-surface border border-surface-hover p-3">
                                <div className="flex items-center justify-between">
                                    <p className="text-xs text-text-dim">{k}</p>
                                    <p className={`text-sm font-bold ${MENU_CLASS[k].tone === "ok" ? "text-emerald-400" : MENU_CLASS[k].tone === "warn" ? "text-red-400" : "text-text"}`}>{v}</p>
                                </div>
                                <p className="text-[10px] text-text-dim mt-1 leading-snug">{MENU_CLASS[k].blurb}</p>
                            </div>
                        ))}
                    </div>

                    {data.category_performance && data.category_performance.length > 0 && (
                        <div className="mb-4">
                            <p className="text-xs font-semibold text-text-muted mb-2">Category performance (share of revenue · margin)</p>
                            <div className="space-y-1.5">
                                {data.category_performance.slice(0, 6).map((c, i) => (
                                    <div key={i} className="flex items-center gap-2 text-xs">
                                        <span className="text-text w-24 flex-shrink-0 truncate">{c.category}</span>
                                        <div className="flex-1 h-1.5 bg-surface-hover rounded-full overflow-hidden">
                                            <div className="h-full bg-[var(--accent)] rounded-full" style={{ width: `${Math.min(c.revenue_share_pct * 3, 100)}%` }} />
                                        </div>
                                        <span className="text-text-muted w-10 text-right">{c.revenue_share_pct}%</span>
                                        <span className={`w-12 text-right ${c.avg_margin_pct >= 55 ? "text-emerald-400" : c.avg_margin_pct >= 40 ? "text-amber-400" : "text-red-400"}`}>{c.avg_margin_pct}%</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {data.recommendations && data.recommendations.length > 0 && (
                        <>
                            <p className="text-xs font-semibold text-text-muted mb-2">Top menu actions</p>
                            <div className="space-y-2">
                                {data.recommendations.slice(0, 5).map((r, i) => (
                                    <div key={i} className="p-3 rounded-lg bg-surface border border-surface-hover text-sm">
                                        <div className="flex items-center gap-2">
                                            <span className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded ${r.priority === "high" ? "bg-red-500/10 text-red-400" : r.priority === "medium" ? "bg-amber-500/10 text-amber-400" : "bg-info/10 text-info"}`}>{r.priority}</span>
                                            <p className="text-text">{r.item} — {r.action}</p>
                                        </div>
                                        <p className="text-xs text-text-dim mt-1">{r.reason}</p>
                                        {r.impact && <p className="text-xs text-emerald-400 mt-0.5">📈 {r.impact}</p>}
                                    </div>
                                ))}
                            </div>
                        </>
                    )}
                </>
            )}
        </ModuleShell>
    );
}
