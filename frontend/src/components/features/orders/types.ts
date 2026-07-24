export interface Order {
    id: number;
    status: string;
    order_type: string;
    customer_name: string;
    table_number: number | null;
    total: number;
    notes: string;
    is_paid: boolean;
    created_at: string;
}

export interface OrderTrends {
    peak_hour?: number;
    peak_day?: string;
    week_over_week_growth?: number;
    total_revenue: number;
    avg_order_value: number;
}

export interface OrderForecastDay {
    predicted?: number;
    amount?: number;
    day_name?: string;
}

export interface OrderAnomaly {
    date: string;
    type: "high" | "low";
    revenue: number;
}

export interface OrderAiData {
    trends: OrderTrends;
    forecast: OrderForecastDay[];
    anomalies: OrderAnomaly[];
}
