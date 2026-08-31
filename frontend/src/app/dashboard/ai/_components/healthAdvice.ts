/**
 * _components/healthAdvice.ts — shared health-score copy + tone helpers.
 * Extracted from HealthBoostSection so the new BusinessHealth panel and the
 * existing "How to raise your health score" section share one source of truth
 * instead of drifting.
 */

export interface HealthDriver {
    category: string;
    score: number;
    detail: string;
}

/** Turns the health breakdown into specific, prioritised "do this next" guidance. */
export const HEALTH_ADVICE: Record<string, (detail: string) => string> = {
    "Menu Health": () => "Rework or remove your 'Dog' items and reprice 'Plowhorses' — see Menu Engineering below. Fewer weak items lifts this fast.",
    "Revenue Trend": () => "Revenue is trending down week-over-week. Run a promo on slow days and push high-margin items to reverse it.",
    "Kitchen Efficiency": () => "Prep times are dragging on the flagged stations. Rebalance staff to the bottleneck stations during peak hours.",
    "Inventory Status": () => "Restock the low items and use up near-expiry stock first (FIFO) to clear spoilage-risk flags.",
    "Reservation Reliability": () => "Cut no-shows with SMS reminders and a small deposit on large parties — that lifts completion and recovers lost covers.",
};

export function healthLabel(score: number): string {
    if (score >= 75) return "Healthy";
    if (score >= 50) return "Needs attention";
    return "At risk";
}

/** Status-dot class for a single driver score (design tokens). */
export function driverDot(score: number): string {
    if (score >= 70) return "bg-success";
    if (score >= 40) return "bg-warning";
    return "bg-danger";
}

/** Text colour matching driverDot, for score numbers. */
export function driverText(score: number): string {
    if (score >= 70) return "text-success";
    if (score >= 40) return "text-warning";
    return "text-danger";
}

/** The n lowest-scoring drivers, ascending (worst first). */
export function worstDrivers(breakdown: HealthDriver[], n = 2): HealthDriver[] {
    return [...breakdown].sort((a, b) => a.score - b.score).slice(0, n);
}

/** Human name for a driver category (matches the home dashboard mapping). */
export function friendlyCategory(category: string): string {
    const map: Record<string, string> = {
        "Menu Health": "Your menu",
        "Revenue Trend": "Revenue",
        "Kitchen Efficiency": "Kitchen",
        "Inventory Status": "Inventory",
        "Reservation Reliability": "Bookings",
    };
    return map[category] || category;
}
