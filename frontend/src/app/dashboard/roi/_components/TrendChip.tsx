"use client";

import { ArrowUpRight, ArrowDownRight } from "lucide-react";

// Small signed-percentage delta chip. Green when up, muted red when down,
// nothing at all when there's no prior baseline (null) — never a fake "0%".
export default function TrendChip({ pct }: { pct?: number | null }) {
    if (pct === null || pct === undefined) return null;
    const up = pct >= 0;
    return (
        <span className={`inline-flex items-center gap-0.5 text-[11px] font-medium ${up ? "text-emerald-400" : "text-red-400"}`}>
            {up ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
            {Math.abs(pct)}% vs prior 30d
        </span>
    );
}
