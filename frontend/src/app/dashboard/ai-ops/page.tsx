"use client";

/**
 * /dashboard/ai-ops — AI Operations (admin only)
 *
 * Surfaces GET /ai/usage (backend/ai/evaluation/tracker.py): how much the AI is
 * "thinking" (LLM calls + tokens by model), how reliable each agent is (runs,
 * success rate, p50/p95 latency), and how trustworthy its figures are (grounding
 * %). Framed for an owner/admin as "what the AI costs and how well it's working"
 * — the honest counterweight to the ROI page's "what it saves."
 *
 * ADMIN-gated on the backend; the nav item only shows for admins, and a 403 here
 * degrades to a friendly notice rather than an error.
 */

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Cpu, RefreshCw, AlertTriangle, ShieldCheck, Activity, Gauge } from "lucide-react";

interface UsageData {
    window_days: number;
    llm: {
        calls: number;
        input_tokens: number;
        output_tokens: number;
        cost_usd?: number;
        cost_per_response_usd?: number;
        by_model: Record<string, { calls: number; input_tokens: number; output_tokens: number; cost_usd?: number }>;
    };
    economics?: {
        llm_cost_usd: number;
        llm_cost_kes_cents: number;
        profit_generated_cents: number;
    };
    agents: { agent: string; runs: number; success_rate_pct: number; p50_ms: number; p95_ms: number }[];
    scorecards?: {
        agent: string;
        prediction_count?: number;
        mae_pct?: number | null;
        ci_coverage_pct?: number | null;
        quality?: string;
        acceptance_rate_pct?: number;
        approved?: number;
        rejected?: number;
    }[];
    grounding: Record<string, any>;
}

function kes(cents: number | null | undefined): string {
    return `KES ${Math.round((cents || 0) / 100).toLocaleString("en-KE")}`;
}

function fmt(n: number | null | undefined): string {
    if (!n) return "0";
    return n.toLocaleString("en-KE");
}

export default function AiOpsPage() {
    const { user } = useAuth();
    const [data, setData] = useState<UsageData | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [forbidden, setForbidden] = useState(false);
    const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

    const fetchData = async () => {
        setLoading(true);
        setError("");
        setForbidden(false);
        try {
            const res = await api.get("/ai/usage?days=30");
            setData(res.data);
            setLastUpdated(new Date());
        } catch (e: any) {
            if (e?.response?.status === 403) setForbidden(true);
            else setError(e?.response?.data?.detail || e?.message || "Could not load AI operations data");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { fetchData(); }, []);

    if (loading) {
        return (
            <div className="space-y-4">
                <div className="bg-[#141414] rounded-xl h-8 w-48 animate-pulse" />
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                    {[...Array(4)].map((_, i) => <div key={i} className="bg-[#141414] rounded-xl h-20 animate-pulse" />)}
                </div>
            </div>
        );
    }

    if (forbidden) {
        return (
            <div className="flex flex-col items-center justify-center min-h-[50vh] space-y-3 text-center">
                <ShieldCheck className="w-10 h-10 text-[var(--accent)]" />
                <p className="text-[#e5e5e5] font-medium">Admins only</p>
                <p className="text-[#525252] text-sm max-w-sm">
                    AI Operations shows sensitive cost and reliability metrics, so it&apos;s limited to admin accounts.
                    You&apos;re signed in as <span className="text-[#a3a3a3]">{user?.role || "a non-admin"}</span>.
                </p>
            </div>
        );
    }

    if (error) {
        return (
            <div className="flex flex-col items-center justify-center min-h-[50vh] space-y-4">
                <AlertTriangle className="w-10 h-10 text-amber-400" />
                <p className="text-[#e5e5e5] font-medium">Could not load AI operations</p>
                <p className="text-[#525252] text-sm text-center max-w-sm">{error}</p>
                <button onClick={fetchData} className="px-4 py-2 bg-[var(--accent)] text-[#0a0a0a] font-semibold rounded-lg text-sm hover:bg-[var(--accent-hover)]">Retry</button>
            </div>
        );
    }

    const d = data!;
    const totalTokens = (d.llm?.input_tokens || 0) + (d.llm?.output_tokens || 0);
    const groundedPct = d.grounding?.grounded_pct ?? d.grounding?.grounding_enabled;
    const models = Object.entries(d.llm?.by_model || {});
    const maxRuns = Math.max(1, ...(d.agents || []).map((a) => a.runs));

    return (
        <div className="space-y-6">
            <div className="flex items-start justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-[#e5e5e5]">AI Operations</h1>
                    <p className="text-[#525252] mt-1 text-sm">How much the AI is using and how well it&apos;s working — last {d.window_days} days</p>
                </div>
                <button onClick={fetchData} className="flex items-center gap-2 px-3 py-2 rounded-lg bg-[#141414] border border-[#262626] text-[#737373] hover:text-[#e5e5e5] text-sm transition-colors">
                    <RefreshCw className="w-3.5 h-3.5" />
                    <span>{lastUpdated ? lastUpdated.toLocaleTimeString() : "Refresh"}</span>
                </button>
            </div>

            <div className="rounded-xl border border-[#1a1a1a] bg-[#0f0f0f] p-4">
                <p className="text-sm text-[#a3a3a3] leading-relaxed">
                    Every figure on the ROI page is computed exactly by the software. The AI is only used to
                    <span className="text-[#e5e5e5]"> explain</span> those numbers in plain words. This page shows how
                    much of that explaining happened, how reliable each analysis agent is, and how many AI-written
                    figures were verified against your real data before you saw them.
                </p>
            </div>

            {/* LLM usage */}
            <div>
                <h2 className="text-sm font-semibold text-[#e5e5e5] flex items-center gap-2 mb-3"><Cpu className="w-4 h-4 text-[var(--accent)]" /> How much the AI is thinking</h2>
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                    <Stat label="AI calls" value={fmt(d.llm?.calls)} />
                    <Stat label="Input tokens" value={fmt(d.llm?.input_tokens)} />
                    <Stat label="Output tokens" value={fmt(d.llm?.output_tokens)} />
                    <Stat label="Figures verified" value={typeof groundedPct === "number" ? `${groundedPct}%` : groundedPct ? "On" : "—"} tone="ok" />
                </div>
                {d.economics && (
                    <div className="rounded-xl border border-[#1a1a1a] bg-[#0f0f0f] p-4 mt-3 flex items-center justify-between flex-wrap gap-2">
                        <div className="text-sm">
                            <span className="text-[#525252]">Tokens used </span>
                            <span className="text-[#e5e5e5] font-medium">{fmt(totalTokens)}</span>
                            <span className="text-[#525252]"> vs. profit captured </span>
                            <span className="text-emerald-400 font-medium">{kes(d.economics.profit_generated_cents)}</span>
                        </div>
                        <p className="text-[10px] text-[#525252]">Profit = approved pricing recommendations.</p>
                    </div>
                )}
                {models.length > 0 && (
                    <div className="rounded-xl border border-[#1a1a1a] bg-[#0f0f0f] p-5 mt-3">
                        <p className="text-xs font-semibold text-[#737373] mb-3">By model</p>
                        <div className="space-y-2">
                            {models.map(([model, m]) => (
                                <div key={model} className="flex items-center justify-between text-sm py-1.5 border-b border-[#1a1a1a] last:border-0">
                                    <span className="text-[#e5e5e5] truncate">{model}</span>
                                    <span className="text-[#525252] text-xs whitespace-nowrap">{fmt(m.calls)} calls · {fmt(m.input_tokens + m.output_tokens)} tokens</span>
                                </div>
                            ))}
                        </div>
                        <p className="text-[11px] text-[#525252] mt-3">Total {fmt(totalTokens)} tokens across {fmt(d.llm?.calls)} calls.</p>
                    </div>
                )}
            </div>

            {/* Agent reliability */}
            <div className="rounded-xl border border-[#1a1a1a] bg-[#0f0f0f] p-5">
                <h2 className="text-sm font-semibold text-[#e5e5e5] flex items-center gap-2 mb-1"><Activity className="w-4 h-4 text-[var(--accent)]" /> Agent reliability</h2>
                <p className="text-xs text-[#525252] mb-4">How often each analysis agent ran, how often it succeeded, and how fast it responded.</p>
                {(!d.agents || d.agents.length === 0) ? (
                    <p className="text-[#525252] text-sm">No agent runs recorded in this window yet.</p>
                ) : (
                    <div className="space-y-3">
                        {d.agents.map((a) => (
                            <div key={a.agent} className="text-sm">
                                <div className="flex items-center justify-between gap-2">
                                    <span className="text-[#e5e5e5]">{a.agent}</span>
                                    <span className="text-[#525252] text-xs whitespace-nowrap flex items-center gap-2">
                                        <span className={a.success_rate_pct >= 95 ? "text-emerald-400" : a.success_rate_pct >= 80 ? "text-amber-400" : "text-red-400"}>{a.success_rate_pct}% ok</span>
                                        <span className="flex items-center gap-1"><Gauge className="w-3 h-3" /> {fmt(a.p50_ms)}ms · p95 {fmt(a.p95_ms)}ms</span>
                                    </span>
                                </div>
                                <div className="mt-1 h-1.5 bg-[#1a1a1a] rounded-full overflow-hidden">
                                    <div className="h-full bg-[var(--accent)] rounded-full" style={{ width: `${Math.round((a.runs / maxRuns) * 100)}%` }} />
                                </div>
                                <p className="text-[10px] text-[#525252] mt-0.5">{fmt(a.runs)} runs</p>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {/* Agent scorecards — accuracy + owner acceptance (measured like an employee) */}
            {d.scorecards && d.scorecards.length > 0 && (
                <div className="rounded-xl border border-[#1a1a1a] bg-[#0f0f0f] p-5">
                    <h2 className="text-sm font-semibold text-[#e5e5e5] flex items-center gap-2 mb-1">
                        <ShieldCheck className="w-4 h-4 text-[var(--accent)]" /> Agent scorecards
                    </h2>
                    <p className="text-xs text-[#525252] mb-4">Forecast accuracy and how often you accept each agent&apos;s advice — measured against reality.</p>
                    <div className="space-y-2">
                        {d.scorecards.map((c) => (
                            <div key={c.agent} className="flex items-center justify-between text-sm py-1.5 border-b border-[#1a1a1a] last:border-0">
                                <span className="text-[#e5e5e5]">{c.agent}</span>
                                <span className="text-xs text-[#525252] flex items-center gap-3 whitespace-nowrap">
                                    {typeof c.acceptance_rate_pct === "number" && (
                                        <span className={c.acceptance_rate_pct >= 60 ? "text-emerald-400" : "text-amber-400"}>
                                            {c.acceptance_rate_pct}% accepted ({c.approved}/{(c.approved || 0) + (c.rejected || 0)})
                                        </span>
                                    )}
                                    {typeof c.mae_pct === "number" && (
                                        <span className={c.mae_pct <= 10 ? "text-emerald-400" : c.mae_pct <= 20 ? "text-amber-400" : "text-red-400"}>
                                            {c.mae_pct}% avg error · {c.prediction_count} scored
                                        </span>
                                    )}
                                    {typeof c.ci_coverage_pct === "number" && (
                                        <span>{c.ci_coverage_pct}% in range</span>
                                    )}
                                </span>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}

function Stat({ label, value, tone }: { label: string; value: string | number; tone?: "ok" }) {
    return (
        <div className="rounded-xl border border-[#1a1a1a] bg-[#0f0f0f] p-4">
            <p className="text-xs text-[#525252] mb-1">{label}</p>
            <p className={`text-xl font-bold ${tone === "ok" ? "text-emerald-400" : "text-[#e5e5e5]"}`}>{value}</p>
        </div>
    );
}
