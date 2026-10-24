"use client";

/**
 * frontend/src/components/ai/NarrativeBlock.tsx
 * ──────────────────────────────────────────────
 * Renders the backend reasoning layer's plain-language interpretation
 * (ai/reasoning/narrator.py) with a trust badge. The figures in each module are
 * computed deterministically; this is the LLM's *interpretation* of them, with
 * every number it cites already grounding-checked server-side. `verified` means
 * every figure the model wrote was found in the real data; if not, the backend
 * has already redacted the bad figures and we surface how many were removed — so
 * the badge is an honest trust signal, not decoration.
 */

import { useState } from "react";
import { Sparkles, ShieldCheck, ChevronDown } from "lucide-react";

export interface Narrative {
    headline: string;
    priorities: string[];
    actions: { action: string; why?: string; impact?: string }[];
    verified: boolean;
    ungrounded_numbers: string[];
    cached?: boolean;
}

export function NarrativeBlock({ n }: { n?: Narrative }) {
    const [showTrust, setShowTrust] = useState(false);
    if (!n || (!n.headline && (!n.priorities || n.priorities.length === 0))) return null;
    const headline = (n.headline || "").replace(/\[unverified\]/gi, "").replace(/\bfigures removed\b/gi, "").trim();
    const priorities = (n.priorities || []).map((p) => p.replace(/\[unverified\]/gi, "").trim()).filter((p) => p && !/figures removed/i.test(p));
    if (!headline && priorities.length === 0) return null;
    return (
        <div className="mb-4 rounded-lg border border-[var(--accent)]/25 bg-[var(--accent)]/[0.04] p-4">
            <div className="flex items-start justify-between gap-3 mb-2">
                <div className="flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-[var(--accent)]" />
                    <span className="text-xs font-semibold uppercase tracking-wide text-[var(--accent)]">AI reading</span>
                </div>
                {n.verified && (
                    <span
                        className="flex items-center gap-1 text-[10px] text-emerald-700 bg-emerald-500/10 border border-emerald-500/20 rounded px-1.5 py-0.5 whitespace-nowrap"
                        title="Every figure cited was checked against your real numbers"
                    >
                        <ShieldCheck className="w-3 h-3" /> Figures checked
                    </span>
                )}
            </div>
            {headline && <p className="text-sm text-text leading-snug">{headline}</p>}
            {priorities.length > 0 && (
                <ul className="mt-2 space-y-1">
                    {priorities.map((p, i) => (
                        <li key={i} className="text-xs text-text-muted flex gap-2">
                            <span className="text-[var(--accent)] flex-shrink-0">•</span>
                            <span>{p}</span>
                        </li>
                    ))}
                </ul>
            )}
            {n.actions && n.actions.length > 0 && (
                <div className="mt-2 space-y-1">
                    {n.actions.slice(0, 3).map((a, i) => (
                        <p key={i} className="text-xs text-[#737373]">
                            <span className="text-[#e5e5e5]">→ {a.action}</span>
                            {a.why ? ` — ${a.why}` : ""}
                        </p>
                    ))}
                </div>
            )}
            <button
                onClick={() => setShowTrust((v) => !v)}
                className="mt-2 flex items-center gap-1 text-[10px] text-[#525252] italic hover:text-[#737373] transition-colors"
            >
                AI interpretation · the figures above are computed exactly, not by the AI.
                <ChevronDown className={`w-2.5 h-2.5 transition-transform ${showTrust ? "rotate-180" : ""}`} />
            </button>
            {showTrust && (
                <div className="mt-1.5 rounded-md border border-[#1a1a1a] bg-[#0a0a0a] p-2.5 space-y-1.5">
                    <p className="text-[11px] text-[#a3a3a3] leading-relaxed">
                        The &quot;AI reading&quot; is only the AI&apos;s opinion in words. Every number is calculated
                        exactly by the system — never made up by the AI.
                    </p>
                    <p className="text-[11px] text-[#737373] leading-snug flex gap-1.5">
                        <ShieldCheck className="w-3 h-3 flex-shrink-0 mt-0.5 text-emerald-400" />
                        <span><span className="text-[#e5e5e5] font-medium">Figures checked</span> — every number the AI wrote was found in your real data.</span>
                    </p>
                </div>
            )}
        </div>
    );
}
