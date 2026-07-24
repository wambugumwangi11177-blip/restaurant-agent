"use client";

import { Info } from "lucide-react";

interface RoiBreakdownItem {
    category: string;
    count: number;
    minutes_per_action: number;
    total_minutes: number;
}

const CATEGORY_LABELS: Record<string, string> = {
    morning_briefing: "Morning briefings sent",
    reservation_reminder: "Reservation reminders sent",
    no_show_winback: "No-show win-back messages",
    receipt: "Receipts sent",
    promo: "Promo messages sent",
    campaign_winback: "Win-back campaign messages",
    feedback_alert: "Feedback alerts handled",
    slow_day_alert: "Slow-day alerts sent",
    reorder_request: "Reorder requests sent",
    supplier_late: "Supplier delay alerts",
    stock_depleted: "Stock-out alerts",
    orchestrated_stock_critical: "Critical stock alerts",
    pricing_intelligence: "Pricing analysis runs",
    labor_intelligence: "Labor analysis runs",
    profit_intelligence: "Profit analysis runs",
    inventory_predictor: "Inventory analysis runs",
    supply_chain_intelligence: "Supplier analysis runs",
};

// Plain-language "what a staff member would have done by hand" for each
// automated action — the reason it saves the minutes it does. Faithful to the
// audit comments in backend/ai/roi/savings.py.
const CATEGORY_WHY: Record<string, string> = {
    morning_briefing: "A manager compiling the day's numbers by hand every morning.",
    reservation_reminder: "A staff member calling or texting each guest to confirm.",
    no_show_winback: "Someone calling a no-show to re-book them.",
    receipt: "Manually texting or printing each receipt.",
    promo: "Writing and sending one promo message.",
    campaign_winback: "Drafting and sending one win-back message.",
    feedback_alert: "Noticing a bad review and deciding what to do.",
    slow_day_alert: "Spotting a slow day early enough to react.",
    reorder_request: "Checking stock and messaging a supplier to reorder.",
    supplier_late: "Chasing a late supplier delivery.",
    stock_depleted: "Realising an item ran out and alerting the floor.",
    orchestrated_stock_critical: "Catching a critical stock-out before service.",
    pricing_intelligence: "A manual competitor / margin repricing pass.",
    labor_intelligence: "A manual overtime and scheduling review.",
    profit_intelligence: "A manual contribution-margin analysis.",
    inventory_predictor: "A manual stock-level review.",
    supply_chain_intelligence: "A manual supplier-performance review.",
};

export default function RoiBreakdown({ breakdown, hoursSaved30d }: { breakdown: RoiBreakdownItem[]; hoursSaved30d: number }) {
    return (
        <div className="rounded-xl border border-surface-hover bg-[#0f0f0f] p-5">
            <p className="text-text font-semibold text-sm mb-1">
                Where the {hoursSaved30d} hours came from
            </p>
            <p className="text-text-dim text-xs mb-4">
                Each row is work the AI did automatically. Hover the info dot to see what a
                staff member would have done by hand.
            </p>
            {breakdown.length === 0 ? (
                <p className="text-text-dim text-sm">No automated activity in this window.</p>
            ) : (
                <div className="space-y-2">
                    {breakdown.map((b, i) => (
                        <div key={i} className="flex items-center justify-between text-sm py-2 border-b border-surface-hover last:border-0 gap-3">
                            <span className="text-[#a3a3a3] flex items-center gap-1.5 min-w-0">
                                <span className="truncate">{CATEGORY_LABELS[b.category] || b.category}</span>
                                {CATEGORY_WHY[b.category] && (
                                    <span title={CATEGORY_WHY[b.category]} className="flex-shrink-0">
                                        <Info className="w-3 h-3 text-text-dim" />
                                    </span>
                                )}
                                <span className="text-text-dim whitespace-nowrap"> · {b.count}× at {b.minutes_per_action} min</span>
                            </span>
                            <span className="text-text font-medium whitespace-nowrap">{Math.round(b.total_minutes / 60 * 10) / 10} hrs</span>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
