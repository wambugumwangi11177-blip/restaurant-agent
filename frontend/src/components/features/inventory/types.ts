export interface InventoryItem {
    id: number;
    item_name: string;
    quantity: number;
    unit: string;
    cost_per_unit: number;
    low_stock_threshold: number;
}

export interface StockTransfer {
    id: number;
    from_location: string;
    to_location: string;
    quantity: number;
    unit: string;
    status: string;
}

export interface VarianceItem {
    id: number;
    inventory_item_id: number;
    item_name: string;
    theoretical_usage: number;
    actual_usage: number;
    variance_pct: number;
    flagged: boolean;
}

export interface InventoryPrediction {
    item_name: string;
    abc_class?: string;
    days_until_stockout?: number;
}

export interface VarianceReport {
    threshold: number;
    items: VarianceItem[];
}

export interface StockAlert {
    message: string;
    action?: string;
}

export interface InventorySummary {
    total_items: number;
    critical_items: number;
    low_stock_items: number;
    high_spoilage_items: number;
    monthly_spend: number;
}

export interface InventoryAiData {
    summary: InventorySummary;
    predictions: InventoryPrediction[];
    alerts: StockAlert[];
}
