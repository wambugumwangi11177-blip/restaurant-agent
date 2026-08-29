"use client";

import Link from "next/link";
import { Shield, CheckCircle, ArrowRight } from "lucide-react";
import { useAiModule } from "@/lib/useAiModule";
import { ModuleShell } from "@/components/ai/ModuleShell";
import { MiniStat } from "@/components/ai/MiniStat";

// Cost-price data-quality guard. Every profit/pricing figure divides by cost_price;
// this surfaces the items silently breaking those numbers so the owner fixes the
// input, not the output. Backed by GET /ai/data-quality (ai/data_quality.py).
const DQ_ISSUE_LABEL: Record<string, string> = {
    MISSING_COST: "No cost price set",
    MISSING_PRICE: "No sale price set",
    SELLING_AT_LOSS: "Sold at a loss",
    SUSPICIOUSLY_LOW_COST: "Cost looks like a typo",
    THIN_MARGIN: "Very thin margin",
};

interface DQData {
    summary: { total_items: number; items_with_issues: number; missing_cost_count: number; coverage_pct: number; high_severity_count: number };
    issues: { item_id: number; item_name: string; category: string; price: number; cost_price: number; qty_30d: number; issue: string; severity: string; explanation: string }[];
}

export default function DataQualitySection() {
    const { data, loading, error, retry } = useAiModule<DQData>("/ai/data-quality");

    return (
        <ModuleShell icon={Shield} title="Cost-Price Data Check" explainKey="dataquality" loading={loading} error={error} onRetry={retry}
            subtitle="Your profit & pricing numbers are only as accurate as the cost prices you enter — this flags the gaps.">
            {data && (
                <>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
                        <MiniStat label="Cost-price coverage" value={`${data.summary.coverage_pct}%`} tone={data.summary.coverage_pct >= 90 ? "ok" : "warn"} />
                        <MiniStat label="Items to fix" value={data.summary.items_with_issues} tone={data.summary.items_with_issues > 0 ? "warn" : "ok"} />
                        <MiniStat label="Missing cost" value={data.summary.missing_cost_count} tone={data.summary.missing_cost_count > 0 ? "warn" : "ok"} />
                        <MiniStat label="High severity" value={data.summary.high_severity_count} tone={data.summary.high_severity_count > 0 ? "warn" : "ok"} />
                    </div>
                    {data.issues.length === 0 ? (
                        <p className="text-emerald-400 text-sm flex items-center gap-2">
                            <CheckCircle className="w-4 h-4" /> Cost prices look healthy — your profit numbers can be trusted.
                        </p>
                    ) : (
                        <div className="space-y-2">
                            {data.issues.slice(0, 6).map((i) => (
                                <div key={i.item_id} className="p-3 rounded-lg bg-surface border border-surface-hover text-sm">
                                    <div className="flex items-center justify-between gap-2">
                                        <div className="flex items-center gap-2 flex-wrap">
                                            <span className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded ${i.severity === "HIGH" ? "bg-red-500/10 text-red-400" : i.severity === "MEDIUM" ? "bg-amber-500/10 text-amber-400" : "bg-info/10 text-[#60a5fa]"}`}>{DQ_ISSUE_LABEL[i.issue] || i.issue}</span>
                                            <p className="text-text">{i.item_name}</p>
                                        </div>
                                        {i.qty_30d > 0 && <span className="text-xs text-text-dim whitespace-nowrap">{i.qty_30d} sold/30d</span>}
                                    </div>
                                    <p className="text-xs text-text-dim mt-1">{i.explanation}</p>
                                </div>
                            ))}
                            <Link href="/dashboard/menu" className="inline-flex items-center gap-1 text-xs text-[var(--accent)] hover:underline mt-1">
                                Fix in Menu <ArrowRight className="w-3 h-3" />
                            </Link>
                        </div>
                    )}
                </>
            )}
        </ModuleShell>
    );
}
