export interface Reservation {
    id: number;
    customer_name: string;
    customer_phone: string;
    party_size: number;
    reservation_date: string;
    reservation_time: string;
    status: string;
    notes: string;
    table_id: number | null;
}

export interface FloorTable {
    id: number;
    table_id?: number;
    table_number: number;
    capacity: number;
    status: string;
}

export interface ReservationRecommendation {
    message: string;
    action?: string;
    estimated_impact?: string;
}

export interface ReservationAiData {
    no_show_analysis?: { no_show_rate?: number };
    revenue_impact?: { estimated_revenue_lost?: number };
    deposit_effectiveness?: { with_deposit_no_show_rate?: number; without_deposit_no_show_rate?: number };
    table_utilization?: { avg_utilization?: number };
    overbooking?: { recommended_rate?: number; potential_monthly_recovery?: number };
    recommendations?: ReservationRecommendation[];
}
