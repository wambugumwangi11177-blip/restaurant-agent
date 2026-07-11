"use client";

/**
 * frontend/src/components/ai/MiniStat.tsx
 * A small labelled stat tile with an optional ok/warn tone. Shared by the AI
 * Command Center module sections and the Marketing page.
 */

export function MiniStat({ label, value, tone }: { label: string; value: string | number; tone?: "ok" | "warn" }) {
    const color = tone === "warn" ? "text-red-400" : tone === "ok" ? "text-emerald-400" : "text-[#e5e5e5]";
    return (
        <div className="rounded-lg bg-[#141414] border border-[#1a1a1a] p-3">
            <p className="text-xs text-[#525252] mb-1">{label}</p>
            <p className={`text-sm font-bold ${color}`}>{value}</p>
        </div>
    );
}
