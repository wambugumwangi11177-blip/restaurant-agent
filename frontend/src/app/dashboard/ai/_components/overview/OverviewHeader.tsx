"use client";

/**
 * overview/OverviewHeader.tsx — greeting + page title + refresh.
 * Renamed from "AI Command Center": the owner sees "{Restaurant} Overview",
 * greeted by time of day, with AI invisible in the framing.
 */
import { RefreshCw } from "lucide-react";

function greeting(): string {
    const h = new Date().getHours();
    if (h < 12) return "Good morning";
    if (h < 17) return "Good afternoon";
    return "Good evening";
}

export default function OverviewHeader({
    restaurantName,
    lastUpdated,
    onRefresh,
}: {
    restaurantName: string;
    lastUpdated: Date | null;
    onRefresh: () => void;
}) {
    return (
        <div className="flex items-start justify-between gap-4">
            <div>
                <p className="text-sm text-text-dim">{greeting()}</p>
                <h1 className="text-2xl font-bold text-text mt-0.5">{restaurantName} Overview</h1>
            </div>
            <button
                onClick={onRefresh}
                className="flex items-center gap-2 px-3 py-2 rounded-lg bg-surface border border-border text-text-muted hover:text-text text-sm transition-colors"
            >
                <RefreshCw className="w-3.5 h-3.5" />
                <span>{lastUpdated ? lastUpdated.toLocaleTimeString() : "Refresh"}</span>
            </button>
        </div>
    );
}
