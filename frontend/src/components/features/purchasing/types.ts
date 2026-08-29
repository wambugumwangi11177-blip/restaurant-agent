export interface PurchasingItem {
    id: number;
    item_name: string;
    unit: string;
    par_level: number | null;
    default_supplier_id: number | null;
}

export interface Supplier {
    id: number;
    name: string;
    contact_phone: string;
    avg_lead_days: number;
    reliability_score: number | null;
    notes: string;
}

export interface PurchaseOrder {
    id: number;
    item_name: string;
    quantity_ordered: number;
    unit: string;
    status: string;
    notes: string;
    supplier_name: string;
}
