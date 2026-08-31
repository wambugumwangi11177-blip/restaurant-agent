/**
 * overview/taxonomy.ts — one classification layer for everything the
 * Overview surfaces as "needs your attention".
 *
 * The backend emits lowercase severities ("critical", "high", "medium", ...)
 * while the old Command Center compared against UPPERCASE keys, so its
 * top-risk sort silently matched nothing. This module normalises case in one
 * place and maps every signal into four owner-facing classes:
 *
 *   critical    something is wrong right now        (ALERT)
 *   warning     something may become wrong           (WARNING)
 *   opportunity something could be improved          (OPPORTUNITY)
 *   information something happened                   (INFORMATION)
 */

export type AlertClass = "critical" | "warning" | "opportunity" | "information";
export type AttentionKind = "risk" | "alert" | "opportunity";

/** One unified item rendered by the Needs-Attention hero / insight lists. */
export interface AttentionItem {
    kind: AttentionKind;
    cls: AlertClass;
    title: string;
    detail: string;
    /** alert.source ("inventory" | "kitchen" | "menu" | "reservations") when present */
    source?: string;
    /** alert.action hint from the backend, when present */
    actionHint?: string;
    /** opportunity.potential ("high" | "medium") when present */
    potential?: string;
    /** raw backend severity, kept for tie-break sorting */
    rawSeverity: string;
}

// Lower is more urgent. Used to order the merged attention list.
const CLASS_ORDER: Record<AlertClass, number> = {
    critical: 0,
    warning: 1,
    opportunity: 2,
    information: 3,
};

// Secondary tie-break inside a class, from the raw backend severity token.
const RAW_RANK: Record<string, number> = {
    critical: 0,
    high: 1,
    warning: 2,
    medium: 2,
    low: 3,
    info: 3,
    "": 4,
};

export function classify(raw: string | undefined, kind: AttentionKind): AlertClass {
    if (kind === "opportunity") return "opportunity";
    const s = (raw || "").trim().toLowerCase();
    if (s === "critical" || s === "high") return "critical";
    if (s === "medium" || s === "warning") return "warning";
    return "information"; // low / info / empty
}

/** Chip styling per class — design tokens, matches the SectionCard chip rhythm. */
export const CLASS_CHIP: Record<AlertClass, string> = {
    critical: "bg-danger/10 text-danger",
    warning: "bg-warning/10 text-warning",
    opportunity: "bg-success/10 text-success",
    information: "bg-info/10 text-info",
};

/** Small status dot per class (health drivers, list markers). */
export const CLASS_DOT: Record<AlertClass, string> = {
    critical: "bg-danger",
    warning: "bg-warning",
    opportunity: "bg-success",
    information: "bg-info",
};

/** Left-edge accent per class, for hero rows. */
export const CLASS_EDGE: Record<AlertClass, string> = {
    critical: "border-l-danger",
    warning: "border-l-warning",
    opportunity: "border-l-success",
    information: "border-l-info",
};

export const CLASS_LABEL: Record<AlertClass, string> = {
    critical: "Critical",
    warning: "Warning",
    opportunity: "Opportunity",
    information: "Info",
};

export interface AttentionCounts {
    critical: number;
    warning: number;
    opportunity: number;
    information: number;
}

export function groupCounts(items: AttentionItem[]): AttentionCounts {
    const counts: AttentionCounts = { critical: 0, warning: 0, opportunity: 0, information: 0 };
    for (const it of items) counts[it.cls] += 1;
    return counts;
}

interface RiskIn { severity: string; risk: string; detail: string }
interface AlertIn { source: string; item: string; message: string; severity: string; action: string }
interface OpportunityIn { opportunity: string; potential: string; detail: string }

/**
 * Merge risks + alerts + opportunities into one ranked attention list.
 * Order: class urgency first, then raw severity, opportunities after problems.
 */
export function rankAttention(
    risks: RiskIn[] | undefined,
    alerts: AlertIn[] | undefined,
    opportunities: OpportunityIn[] | undefined
): AttentionItem[] {
    const items: AttentionItem[] = [];

    for (const r of risks || []) {
        items.push({
            kind: "risk",
            cls: classify(r.severity, "risk"),
            title: r.risk,
            detail: r.detail,
            rawSeverity: (r.severity || "").toLowerCase(),
        });
    }
    for (const a of alerts || []) {
        items.push({
            kind: "alert",
            cls: classify(a.severity, "alert"),
            title: a.message,
            detail: a.action || "",
            source: a.source,
            actionHint: a.action,
            rawSeverity: (a.severity || "").toLowerCase(),
        });
    }
    for (const o of opportunities || []) {
        items.push({
            kind: "opportunity",
            cls: "opportunity",
            title: o.opportunity,
            detail: o.detail,
            potential: o.potential,
            rawSeverity: (o.potential || "").toLowerCase(),
        });
    }

    return items.sort((a, b) => {
        const byClass = CLASS_ORDER[a.cls] - CLASS_ORDER[b.cls];
        if (byClass !== 0) return byClass;
        const ra = RAW_RANK[a.rawSeverity] ?? 5;
        const rb = RAW_RANK[b.rawSeverity] ?? 5;
        return ra - rb;
    });
}
