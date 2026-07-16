"use client";

/**
 * frontend/src/components/ai/DigitalTwin.tsx
 * Forward revenue projection from GET /ai/forecast/twin. Shows the sales-history
 * baseline vs the signal-adjusted projection, the uplift, a confidence band, and
 * the specific upcoming days a holiday / school break is expected to move.
 */

import { useState } from "react";
import { Sparkles } from "lucide-react";
import { useAiModule } from "@/lib/useAiModule";
import { formatKES } from "@/lib/format";
import { MiniStat } from "./MiniStat";
import { HowItWorks } from "./HowItWorks";
import { ModuleShell } from "./ModuleShell";

interface TwinData {
    available: boolean;
    horizon_days: number;
    summary: {
        baseline_revenue_cents: number;
        projected_revenue_cents: number;
        uplift_cents: number;
        uplift_pct: number;
        low_cents: number;
        high_cents: number;
        confidence_pct: number;
        signal_days: number;
    };
    contributing_factors: { date: string; reasons: string[]; projected_cents: number; baseline_cents: number }[];
}

export function DigitalTwin() {
    const [horizon, setHorizon] = useState(30);
    const { data, loading, error, retry } = useAiModule<TwinData>(`/ai/forecast/twin?horizon=${horizon}`);

    return (
        <ModuleShell
            icon={Sparkles}
            title="Digital Twin — Revenue Forecast"
            subtitle="Your sales pattern plus holidays & school breaks, projected forward"
            explainKey="twin"
            loading={loading}
            error={error}
            onRetry={retry}
        >
            {data?.available && (
                <>
                    <div className="flex gap-2 mb-4">
                        {[7, 30, 90].map((h) => (
                            <button
                                key={h}
                                onClick={() => setHorizon(h)}
                                className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${
                                    horizon === h
                                        ? "border-[var(--accent)]/40 text-[var(--accent)] bg-[var(--accent)]/10"
                                        : "border-[#1a1a1a] text-[#737373] hover:text-[#e5e5e5]"
                                }`}
                            >
                                {h}d
                            </button>
                        ))}
                    </div>

                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
                        <MiniStat label="Baseline" value={formatKES(data.summary.baseline_revenue_cents)} />
                        <MiniStat label="Projected" value={formatKES(data.summary.projected_revenue_cents)} />
                        <MiniStat label="Uplift" value={`+${formatKES(data.summary.uplift_cents)} (${data.summary.uplift_pct}%)`} />
                        <MiniStat label="Confidence" value={`${data.summary.confidence_pct}%`} />
                    </div>

                    <p className="text-[11px] text-[#525252] mb-3">
                        Range: {formatKES(data.summary.low_cents)} – {formatKES(data.summary.high_cents)} over {data.horizon_days} days
                    </p>

                    {data.contributing_factors.length === 0 ? (
                        <p className="text-[#525252] text-sm">No holidays or school breaks in this window — steady as she goes.</p>
                    ) : (
                        <div className="space-y-1.5">
                            <p className="text-[10px] uppercase tracking-wide text-[#525252]">Upcoming demand movers</p>
                            {data.contributing_factors.slice(0, 6).map((f) => (
                                <div key={f.date} className="flex items-center justify-between text-sm gap-3">
                                    <div className="min-w-0">
                                        <span className="text-[#e5e5e5]">{f.date}</span>
                                        <span className="text-xs text-[#525252] ml-2">{f.reasons.join(", ")}</span>
                                    </div>
                                    <span className="text-emerald-400 text-xs whitespace-nowrap">
                                        +{formatKES(f.projected_cents - f.baseline_cents)}
                                    </span>
                                </div>
                            ))}
                        </div>
                    )}
                </>
            )}
        </ModuleShell>
    );
}
