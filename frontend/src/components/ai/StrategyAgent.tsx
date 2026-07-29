"use client";

/**
 * frontend/src/components/ai/StrategyAgent.tsx
 * The CEO / Strategy agent panel. Type a goal, get one prioritized plan back
 * from POST /ai/strategy, with an expandable reasoning trace (which agents were
 * consulted). Works with or without an LLM key — the backend degrades to the
 * deterministic ranked plan, and this UI renders either identically.
 */

import { useState } from "react";
import { Target, ChevronDown } from "lucide-react";
import api from "@/lib/api";
import { HowItWorks } from "./HowItWorks";

interface Step { action: string; why?: string; expected_impact?: string; priority_score?: number; category?: string; }
interface StrategyResult {
    available: boolean;
    error?: string;
    mode?: "llm" | "deterministic";
    goal?: string;
    strategy?: { headline: string; steps: Step[]; risks: string[] };
    trace?: { tool: string; summary?: string }[];
    note?: string;
    tokens?: { input: number; output: number; model: string };
}

const SUGGESTIONS = [
    "Increase monthly profit by KES 100,000",
    "Reduce food waste this month",
    "Grow weekend revenue",
];

export function StrategyAgent() {
    const [goal, setGoal] = useState("");
    const [result, setResult] = useState<StrategyResult | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");
    const [showTrace, setShowTrace] = useState(false);

    const run = async (g: string) => {
        if (!g.trim()) return;
        setLoading(true);
        setError("");
        setResult(null);
        try {
            const res = await api.post("/ai/strategy", { goal: g });
            if (res.data?.available === false) setError(res.data.error || "Strategy unavailable.");
            else setResult(res.data);
        } catch (e: any) {
            setError(e?.response?.data?.detail || e?.message || "Strategy failed.");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="rounded-xl border border-[#d4a853]/25 bg-gradient-to-b from-[#d4a853]/[0.05] to-[#0f0f0f] p-5">
            <h2 className="text-sm font-semibold text-[#e5e5e5] flex items-center gap-2">
                <Target className="w-4 h-4 text-[#d4a853]" />
                CEO Strategy Agent
            </h2>
            <p className="text-xs text-[#7e7e7e] mt-1">
                Set a goal — the agent consults every specialist brain and returns one prioritized plan.
            </p>
            <HowItWorks id="strategy" />
            <div className="mb-4" />

            <div className="flex gap-2">
                <input
                    value={goal}
                    onChange={(e) => setGoal(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && run(goal)}
                    placeholder="e.g. Increase monthly profit by KES 100,000"
                    className="flex-1 bg-[#0a0a0a] border border-[#262626] rounded-lg text-sm text-[#e5e5e5] px-3 py-2"
                />
                <button
                    onClick={() => run(goal)}
                    disabled={loading || !goal.trim()}
                    className="bg-[#d4a853] text-[#0a0a0a] font-medium text-sm px-4 py-2 rounded-lg hover:opacity-90 disabled:opacity-40 transition-opacity whitespace-nowrap"
                >
                    {loading ? "Thinking…" : "Build plan"}
                </button>
            </div>
            <div className="flex flex-wrap gap-2 mt-2">
                {SUGGESTIONS.map((s) => (
                    <button
                        key={s}
                        onClick={() => { setGoal(s); run(s); }}
                        className="text-[11px] text-[#8a8a8a] hover:text-[#d4a853] border border-[#1a1a1a] rounded-full px-2.5 py-1 transition-colors"
                    >
                        {s}
                    </button>
                ))}
            </div>

            {error && <p className="text-red-400 text-sm mt-3">{error}</p>}

            {result?.available && result.strategy && (
                <div className="mt-4 space-y-3">
                    <div className="flex items-start gap-2">
                        <p className="text-[#e5e5e5] font-medium text-sm">{result.strategy.headline}</p>
                        {result.mode === "deterministic" && (
                            <span className="text-[9px] uppercase tracking-wide text-[#8a8a8a] border border-[#262626] rounded px-1.5 py-0.5 whitespace-nowrap">
                                ranked
                            </span>
                        )}
                    </div>

                    <ol className="space-y-2">
                        {result.strategy.steps.map((s, i) => (
                            <li key={i} className="rounded-lg border border-[#1a1a1a] bg-[#0a0a0a] p-3">
                                <div className="flex items-start gap-2">
                                    <span className="text-[10px] font-bold text-[#0a0a0a] bg-[#d4a853] rounded-full w-5 h-5 flex items-center justify-center flex-shrink-0">
                                        {i + 1}
                                    </span>
                                    <div className="min-w-0">
                                        <p className="text-sm text-[#e5e5e5]">{s.action}</p>
                                        {s.why && <p className="text-xs text-[#7e7e7e] mt-0.5">{s.why}</p>}
                                        {s.expected_impact && (
                                            <p className="text-xs text-emerald-400 mt-0.5">{s.expected_impact}</p>
                                        )}
                                    </div>
                                </div>
                            </li>
                        ))}
                    </ol>

                    {result.strategy.risks?.length > 0 && (
                        <div className="text-xs text-amber-400/80">
                            <span className="font-medium">Risks:</span> {result.strategy.risks.join("; ")}
                        </div>
                    )}

                    {result.note && <p className="text-[11px] text-[#7e7e7e]">{result.note}</p>}

                    {result.trace && result.trace.length > 0 && (
                        <div>
                            <button
                                onClick={() => setShowTrace((v) => !v)}
                                aria-expanded={showTrace}
                                className="flex items-center gap-1 py-1.5 -my-1.5 text-[11px] text-[#8a8a8a] hover:text-[#d4a853] transition-colors"
                            >
                                <span>Reasoning trace ({result.trace.length})</span>
                                <ChevronDown className={`w-3 h-3 transition-transform ${showTrace ? "rotate-180" : ""}`} />
                            </button>
                            {showTrace && (
                                <ol className="mt-2 space-y-1">
                                    {result.trace.map((t, i) => (
                                        <li key={i} className="text-[11px] text-[#7e7e7e]">
                                            <span className="text-[#8a8a8a]">{t.tool}</span>
                                            {t.summary ? ` — ${t.summary}` : ""}
                                        </li>
                                    ))}
                                </ol>
                            )}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
