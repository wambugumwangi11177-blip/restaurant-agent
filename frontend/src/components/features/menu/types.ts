export interface MenuItem {
    id: number;
    name: string;
    description: string;
    price: number;
    category: string;
    is_available: boolean;
    image_url?: string;
    avg_prep_minutes?: number;
}

export interface MenuInsightsSummary {
    stars: number;
    dogs: number;
    puzzles: number;
    plowhorses: number;
    avg_food_cost_pct: number;
}

export interface MenuRecommendation {
    reason?: string;
    message?: string;
    action?: string;
    estimated_impact?: string;
}

export interface MenuAiItem {
    classification: string;
    margin_pct: number;
}

export interface MenuAiMatrixItem extends MenuAiItem {
    item_id: number;
}

export interface MenuAiData {
    summary: MenuInsightsSummary;
    recommendations: MenuRecommendation[];
    matrix: MenuAiMatrixItem[];
}

export interface RecipeIngredient {
    id: number;
    inventory_item_id: number;
    item_name: string;
    quantity_per_serving: number;
    unit: string;
}

export interface InventoryPickItem {
    id: number;
    item_name: string;
    unit: string;
}
