/**
 * overview/types.ts — the GET /ai/dashboard contract, shared by the page
 * orchestrator and the Overview components. Mirrors the shape built in
 * backend/ai/ops_manager.py:get_operations_dashboard (money is cents).
 *
 * NOTE: `alerts` has always been served by the backend but was previously
 * missing from the page's local interface, so the frontend never rendered it.
 */

export interface QuickStats {
    today_orders: number;
    today_revenue: number;
    yesterday_revenue: number;
    day_over_day_change: number;
    pending_orders: number;
    menu_items: number;
    total_revenue_30d: number;
    avg_order_value: number;
    active_alerts: number;
}

export interface HealthBreakdownItem {
    category: string;
    score: number;
    weight: number;
    detail: string;
}

export interface Risk {
    severity: string;
    risk: string;
    detail: string;
}

export interface SystemAlert {
    source: string;
    item: string;
    message: string;
    severity: string;
    action: string;
}

export interface Opportunity {
    opportunity: string;
    potential: string;
    detail: string;
}

export interface RecentAiAction {
    action: string;
    agent: string;
    time: string;
}

export interface DashboardData {
    health_score: number;
    health_breakdown: HealthBreakdownItem[];
    quick_stats: QuickStats;
    alerts: SystemAlert[];
    risks: Risk[];
    opportunities: Opportunity[];
    ai_modules: { revenue?: { week_over_week_growth?: number } };
    recent_ai_actions: RecentAiAction[];
}
