"use client";

import { Brain } from "lucide-react";
import { formatKES } from "@/lib/format";
import { useAiModule } from "@/lib/useAiModule";
import { NarrativeBlock, type Narrative } from "@/components/ai/NarrativeBlock";
import { MiniStat } from "@/components/ai/MiniStat";
import { ModuleShell } from "@/components/ai/ModuleShell";
import { DecisionCard, type Decision } from "@/components/ai/DecisionCard";

interface DecisionsData {
    summary: {
        total_decisions: number;
        quantified_decisions: number;
        total_monthly_impact_cents: number;
        top_action: string | null;
        by_category: Record<string, number>;
    };
    decisions: Decision[];
    narrative?: Narrative;
}

export default function DecisionsSection() {
    const { data, loading, error, retry } = useAiModule<DecisionsData>("/ai/decisions");

    return (
        <ModuleShell
            icon={Brain}
            title="Decision Intelligence"
            subtitle="Every agent's recommendations, ranked by impact, confidence, risk and effort"
            explainKey="decisions"
            loading={loading}
            error={error}
            onRetry={retry}
        >
            {data && (
                <>
                    <NarrativeBlock n={data.narrative} />
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-4">
                        <MiniStat label="Open Decisions" value={data.summary.total_decisions} />
                        <MiniStat label="Quantified" value={data.summary.quantified_decisions} />
                        <MiniStat label="Total Impact" value={formatKES(data.summary.total_monthly_impact_cents)} />
                    </div>
                    {data.decisions.length === 0 ? (
                        <p className="text-text-dim text-sm">
                            No open decisions right now — every agent is happy with the current setup.
                        </p>
                    ) : (
                        <div className="space-y-2">
                            {data.decisions.slice(0, 8).map((d, i) => (
                                <DecisionCard key={`${d.category}-${d.rank}`} d={d} highlight={i === 0} />
                            ))}
                        </div>
                    )}
                </>
            )}
        </ModuleShell>
    );
}
