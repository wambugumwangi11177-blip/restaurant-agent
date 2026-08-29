"use client";

import { useState } from "react";
import { TrendingUp, Check, X, AlertTriangle } from "lucide-react";
import api from "@/lib/api";
import { formatKES } from "@/lib/format";
import { useAiModule } from "@/lib/useAiModule";
import { NarrativeBlock, type Narrative } from "@/components/ai/NarrativeBlock";
import { MiniStat } from "@/components/ai/MiniStat";
import { ModuleShell } from "@/components/ai/ModuleShell";
import { ExplainButton } from "@/components/ai/ExplainButton";
import { getErrorMessage } from "@/lib/errors";

interface PricingRec {
    id?: number;
    status?: string;
    item_id: number;
    item_name: string;
    type: string;
    current_price: number;
    suggested_price: number;
    monthly_impact_cents: number;
    reason: string;
    data_days?: number;
    has_velocity_data?: boolean;
}

interface PricingData {
    summary: { surge_opportunities: number; reprice_needed: number; stimulate_candidates: number; total_revenue_opportunity_cents: number; items_analysed: number };
    recommendations: PricingRec[];
    narrative?: Narrative;
}

export default function PricingSection() {
    const { data, loading, error, retry } = useAiModule<PricingData>("/ai/pricing");

    // Approve/reject wiring. `/ai/pricing` now returns each recommendation with a
    // persisted `id` (see backend sync_pending_recommendations); approving posts
    // to /ai/pricing/{id}/approve (which updates the live menu price and feeds the
    // ROI "profit captured" figure), then refetches so the actioned rec drops off.
    const [actioningId, setActioningId] = useState<number | null>(null);
    const [notice, setNotice] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

    const act = async (rec: PricingRec, action: "approve" | "reject") => {
        if (!rec.id) return;
        setActioningId(rec.id);
        setNotice(null);
        try {
            const res = await api.post(`/ai/pricing/${rec.id}/${action}`);
            if (res.data?.error) {
                setNotice({ kind: "err", text: res.data.error });
            } else {
                setNotice({
                    kind: "ok",
                    text: res.data?.message
                        || (action === "approve"
                            ? `${rec.item_name} price updated`
                            : `${rec.item_name} recommendation dismissed`),
                });
            }
            retry(); // re-materialize: the actioned rec is no longer PENDING
        } catch (e) {
            setNotice({ kind: "err", text: getErrorMessage(e, `Could not ${action} this recommendation`) });
        } finally {
            setActioningId(null);
        }
    };

    return (
        <ModuleShell icon={TrendingUp} title="Pricing Intelligence" explainKey="pricing" loading={loading} error={error} onRetry={retry}
            fullHref="/dashboard/ai/pricing">
            {data && (
                <>
                    <NarrativeBlock n={data.narrative} />
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
                        <MiniStat label="Surge" value={data.summary.surge_opportunities} />
                        <MiniStat label="Reprice" value={data.summary.reprice_needed} />
                        <MiniStat label="Stimulate" value={data.summary.stimulate_candidates} />
                        <MiniStat label="Opportunity" value={formatKES(data.summary.total_revenue_opportunity_cents)} />
                    </div>
                    {notice && (
                        <div className={`mb-3 flex items-center gap-2 rounded-lg px-3 py-2 text-xs ${notice.kind === "ok" ? "bg-emerald-500/10 text-emerald-300" : "bg-red-500/10 text-red-300"}`}>
                            {notice.kind === "ok" ? <Check className="w-3.5 h-3.5 flex-shrink-0" /> : <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />}
                            <span>{notice.text}</span>
                        </div>
                    )}
                    {data.recommendations.length === 0 ? (
                        <p className="text-text-dim text-sm">No pricing changes recommended right now — {data.summary.items_analysed} items analysed.</p>
                    ) : (
                        <div className="space-y-2">
                            {data.recommendations.slice(0, 5).map((r) => {
                                // "Early signal" badge: pricing needs 14+ days of history before it
                                // trusts demand-based moves (SURGE/STIMULATE). has_velocity_data=false
                                // (or data_days < 14) means treat this as a lighter signal.
                                const earlySignal = r.has_velocity_data === false || (typeof r.data_days === "number" && r.data_days < 14);
                                const busy = actioningId === r.id;
                                return (
                                    <div key={r.id ?? r.item_id} className="flex items-center justify-between py-2 border-b border-surface-hover last:border-0 text-sm gap-3">
                                        <div className="min-w-0">
                                            <div className="flex items-center gap-2 flex-wrap">
                                                <p className="text-text">{r.item_name}</p>
                                                {/* Worked example in the owner's own numbers */}
                                                <span className="text-[11px] text-text-muted whitespace-nowrap">
                                                    KES {(r.current_price / 100).toLocaleString()} → <span className="text-[var(--accent)]">KES {(r.suggested_price / 100).toLocaleString()}</span>
                                                </span>
                                                {earlySignal && (
                                                    <span
                                                        className="text-[9px] font-medium uppercase tracking-wide px-1.5 py-0.5 rounded bg-info/10 text-[#60a5fa] whitespace-nowrap"
                                                        title={typeof r.data_days === "number" ? `Only ${r.data_days} days of data so far` : "Limited history — treat as an early signal"}
                                                    >
                                                        early signal
                                                    </span>
                                                )}
                                            </div>
                                            <p className="text-xs text-text-dim mt-0.5">{r.reason}</p>
                                            <ExplainButton item={r} label={`Pricing ${r.type} for ${r.item_name}`} />
                                        </div>
                                        <div className="flex items-center gap-3 flex-shrink-0">
                                            <span className="text-emerald-400 text-xs font-medium whitespace-nowrap">+{formatKES(r.monthly_impact_cents)}/mo</span>
                                            {r.id && (
                                                <div className="flex items-center gap-1.5">
                                                    <button
                                                        onClick={() => act(r, "approve")}
                                                        disabled={busy}
                                                        title="Apply this price to your live menu"
                                                        className="flex items-center gap-1 px-2.5 py-1 rounded-md bg-emerald-500/15 text-emerald-300 hover:bg-emerald-500/25 disabled:opacity-40 disabled:cursor-not-allowed text-xs font-medium transition-colors"
                                                    >
                                                        <Check className="w-3.5 h-3.5" /> Apply
                                                    </button>
                                                    <button
                                                        onClick={() => act(r, "reject")}
                                                        disabled={busy}
                                                        title="Dismiss this recommendation"
                                                        aria-label="Dismiss this recommendation"
                                                        className="flex items-center justify-center w-7 h-7 rounded-md bg-surface-hover text-text-muted hover:text-red-300 hover:bg-red-500/10 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                                                    >
                                                        <X className="w-3.5 h-3.5" />
                                                    </button>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </>
            )}
        </ModuleShell>
    );
}
