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
import { Sparkles, ShieldCheck, ShieldAlert, ChevronDown } from "lucide-react";

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
    const redacted = n.ungrounded_numbers?.length || 0;
    return (
        <div className="mb-4 rounded-lg border border-[#d4a853]/25 bg-[#d4a853]/[0.04] p-4">
            <div className="flex items-start justify-between gap-3 mb-2">
                <div className="flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-[#d4a853]" />
                    <span className="text-xs font-semibold uppercase tracking-wide text-[#d4a853]">AI reading</span>
                </div>
                {n.verified ? (
                    <span
                        className="flex items-center gap-1 text-[10px] text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 rounded px-1.5 py-0.5 whitespace-nowrap"
                        title="Every figure cited was checked against your real numbers"
                    >
                        <ShieldCheck className="w-3 h-3" /> Figures checked
                    </span>
                ) : (
                    <span
                        className="flex items-center gap-1 text-[10px] text-amber-400 bg-amber-500/10 border border-amber-500/20 rounded px-1.5 py-0.5 whitespace-nowrap"
                        title={`Unverified figure(s) removed: ${n.ungrounded_numbers.join(", ")}`}
                    >
                        <ShieldAlert className="w-3 h-3" /> {redacted} figure{redacted === 1 ? "" : "s"} removed
                    </span>
                )}
            </div>
            {n.headline && <p className="text-sm text-[#e5e5e5] leading-snug">{n.headline}</p>}
            {n.priorities && n.priorities.length > 0 && (
                <ul className="mt-2 space-y-1">
                    {n.priorities.map((p, i) => (
                        <li key={i} className="text-xs text-[#a3a3a3] flex gap-2">
                            <span className="text-[#d4a853] flex-shrink-0">•</span>
                            <span>{p}</span>
                        </li>
                    ))}
                </ul>
            )}
            {n.actions && n.actions.length > 0 && (
                <div className="mt-2 space-y-1">
                    {n.actions.slice(0, 3).map((a, i) => (
                        <p key={i} className="text-xs text-[#8a8a8a]">
                            <span className="text-[#e5e5e5]">→ {a.action}</span>
                            {a.why ? ` — ${a.why}` : ""}
                        </p>
                    ))}
                </div>
            )}
            <button
                onClick={() => setShowTrust((v) => !v)}
                className="mt-2 flex items-center gap-1 text-[10px] text-[#7e7e7e] italic hover:text-[#8a8a8a] transition-colors"
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
                    <p className="text-[11px] text-[#8a8a8a] leading-snug flex gap-1.5">
                        <ShieldCheck className="w-3 h-3 flex-shrink-0 mt-0.5 text-emerald-400" />
                        <span><span className="text-[#e5e5e5] font-medium">Figures checked</span> — every number the AI wrote was found in your real data.</span>
                    </p>
                    <p className="text-[11px] text-[#8a8a8a] leading-snug flex gap-1.5">
                        <ShieldAlert className="w-3 h-3 flex-shrink-0 mt-0.5 text-amber-400" />
                        <span><span className="text-[#e5e5e5] font-medium">Figures removed</span> — a number couldn&apos;t be matched to your data, so it was taken out before you saw it.</span>
                    </p>
                </div>
            )}
        </div>
    );
}
