"use client";

/**
 * AiTabs — the Overview's two views. The whole product is now framed as one
 * business system: **Today** (what's happening right now) and **Insights**
 * (why, and what the data says). The earlier five themed tabs (Summary/Money/
 * Operations/Growth/Trust) exposed internal architecture to the owner; their
 * content lives on inside the Insights tab, grouped but not deleted.
 *
 * Keyboard: real buttons with role="tab"; ArrowLeft/ArrowRight move between
 * them (WAI-ARIA tabs pattern). The active tab is synced to the URL hash so
 * refresh/back keeps it. Legacy hashes (#money, #ops, #growth, #trust,
 * #overview) all resolve to Insights so old bookmarks keep working.
 */
import { KeyboardEvent } from "react";

export const AI_TABS = [
    { id: "today", label: "Today" },
    { id: "insights", label: "Insights" },
] as const;

export type AiTabId = (typeof AI_TABS)[number]["id"];

// Old 5-tab hashes — keep every existing bookmark/deep link landing somewhere
// sensible instead of snapping back to the default.
const LEGACY_INSIGHT_HASHES = new Set(["overview", "money", "ops", "growth", "trust"]);

export function tabFromHash(hash: string): AiTabId {
    const id = hash.replace("#", "");
    if (id === "insights" || LEGACY_INSIGHT_HASHES.has(id)) return "insights";
    return "today";
}

export default function AiTabs({
    active,
    onChange,
}: {
    active: AiTabId;
    onChange: (id: AiTabId) => void;
}) {
    function handleKeyDown(e: KeyboardEvent<HTMLDivElement>) {
        if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
        e.preventDefault();
        const idx = AI_TABS.findIndex((t) => t.id === active);
        const dir = e.key === "ArrowRight" ? 1 : -1;
        const next = AI_TABS[(idx + dir + AI_TABS.length) % AI_TABS.length];
        onChange(next.id);
        document.getElementById(`ai-tab-${next.id}`)?.focus();
    }

    return (
        <div
            role="tablist"
            aria-label="Overview views"
            onKeyDown={handleKeyDown}
            className="flex items-center gap-1 border-b border-[var(--border)] overflow-x-auto"
        >
            {AI_TABS.map((tab) => {
                const isActive = tab.id === active;
                return (
                    <button
                        key={tab.id}
                        id={`ai-tab-${tab.id}`}
                        role="tab"
                        aria-selected={isActive}
                        aria-controls={`ai-panel-${tab.id}`}
                        tabIndex={isActive ? 0 : -1}
                        onClick={() => onChange(tab.id)}
                        className={`px-4 py-2.5 text-sm font-medium whitespace-nowrap border-b-2 -mb-px transition-colors ${
                            isActive
                                ? "border-[var(--accent)] text-[var(--accent)]"
                                : "border-transparent text-[var(--text-muted)] hover:text-[var(--text)]"
                        }`}
                    >
                        {tab.label}
                    </button>
                );
            })}
        </div>
    );
}
