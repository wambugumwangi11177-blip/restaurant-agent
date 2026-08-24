/**
 * Human labels for internal action / message-type keys.
 * Keep in sync with backend/ai/ops_manager.py ACTION_LABELS.
 */

const ACTION_LABELS: Record<string, string> = {
    reorder_now: "Reorder now",
    reorder_soon: "Reorder soon",
    plan_reorder: "Plan a reorder",
    use_or_promote: "Use or promote before it spoils",
    reduce_waste: "Review waste and portions",
    increase_frequency: "Order more often",
    morning_briefing: "Morning briefing sent",
    reservation_reminder: "Reservation reminder sent",
    reservation_reminderwhatsapp: "Reservation reminder sent",
    no_show_winback: "No-show win-back sent",
    receipt: "Receipt sent",
    promo: "Promo sent",
    campaign_winback: "Win-back campaign sent",
    reorder_request: "Reorder request sent",
    supplier_late: "Supplier delay alert",
    stock_depleted: "Stock-out alert",
    orchestrated_stock_critical: "Critical stock alert",
};

export function humanAction(action: string | null | undefined): string {
    if (!action) return "";
    if (ACTION_LABELS[action]) return ACTION_LABELS[action];
    if (action.includes("_") && action === action.toLowerCase()) {
        return action.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
    }
    return action;
}
