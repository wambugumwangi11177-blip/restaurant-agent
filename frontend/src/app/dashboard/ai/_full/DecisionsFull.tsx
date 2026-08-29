"use client";

import { useAiModule } from "@/lib/useAiModule";
import { StatGrid, DataTable, SectionTitle, money, LoadingBlock } from "./shared";

interface Decision { agent: string; category: string; action: string; rationale?: string; confidence_pct?: number; risk?: number; difficulty?: number; impact_cents_month?: number | null; data_sources?: string[] }
interface DecisionsData {
    summary: { total_decisions?: number; quantified_decisions?: number; total_monthly_impact_cents?: number; top_action?: string; by_category?: Record<string, number> };
    decisions: Decision[];
    narrative?: { text?: string } | string | null;
}

export default function DecisionsFull() {
    const { data, loading, error, retry } = useAiModule<DecisionsData>("/ai/decisions?limit=100");
    if (loading) return <LoadingBlock />;
    if (error) return <div className="flex items-center gap-3"><p className="text-text-dim text-sm">{error}</p><button onClick={retry} className="px-3 py-1.5 rounded-lg bg-[var(--accent)] text-bg text-sm font-semibold">Retry</button></div>;
    if (!data) return null;
    const s = data.summary ?? {};
    const byCat = Object.entries(s.by_category ?? {});
    return (
        <div>
            <StatGrid stats={[
                { label: "Open Decisions", value: String(s.total_decisions ?? data.decisions.length) },
                { label: "Quantified", value: String(s.quantified_decisions ?? 0) },
                { label: "Total Impact / mo", value: money(s.total_monthly_impact_cents), tone: "ok" },
                { label: "Categories", value: byCat.map(([k, v]) => `${k}: ${v}`).join(" · ") || "—" },
            ]} />
            {data.narrative && (
                <div className="rounded-xl border border-[var(--accent)]/20 bg-[var(--accent)]/5 p-4 mb-2 text-sm text-text">
                    {typeof data.narrative === "string" ? data.narrative : data.narrative.text || ""}
                </div>
            )}
            <SectionTitle>Every recommendation, ranked</SectionTitle>
            <DataTable
                columns={[
                    { key: "action", label: "Action" },
                    { key: "agent", label: "Agent", render: r => <span className="text-text-dim">{String(r.agent).replace(/_/g, " ")}</span> },
                    { key: "rationale", label: "Why" },
                    { key: "impact_cents_month", label: "Impact / mo", render: r => r.impact_cents_month != null ? money(r.impact_cents_month as number) : "—" },
                    { key: "confidence_pct", label: "Conf.", render: r => `${r.confidence_pct ?? "—"}%` },
                    { key: "risk", label: "Risk" },
                    { key: "difficulty", label: "Effort" },
                ]}
                rows={data.decisions } />
        </div>
    );
}
