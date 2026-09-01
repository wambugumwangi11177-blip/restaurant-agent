// Pure cart math, supporting modifiers, line notes, and tax calculation.

export interface ModifierOption {
    id?: number;
    name: string;
    price_delta_cents: number;
    is_available?: boolean;
}

export interface ModifierGroup {
    id: number;
    name: string;
    min_selection: number;
    max_selection: number;
    is_required: boolean;
    options: ModifierOption[];
}

export interface MenuItem {
    id: number;
    name: string;
    price: number; // in cents
    category: string;
    description?: string;
    is_available?: boolean;
    modifier_groups?: ModifierGroup[];
    prep_station?: string;
}

export interface CartItem {
    id: string; // unique line instance id (e.g. item_id + JSON.stringify(modifiers))
    menuItem: MenuItem;
    quantity: number;
    selectedModifiers: ModifierOption[];
    notes?: string;
}

export function lineUnitPrice(item: MenuItem, modifiers: ModifierOption[] = []): number {
    const modTotal = modifiers.reduce((acc, m) => acc + (m.price_delta_cents || 0), 0);
    return item.price + modTotal;
}

export function makeCartItemId(itemId: number, modifiers: ModifierOption[] = [], notes: string = ""): string {
    const modKey = modifiers.map((m) => m.name).sort().join("|");
    return `${itemId}_${modKey}_${notes.trim()}`;
}

export function addToCart(
    cart: CartItem[],
    item: MenuItem,
    selectedModifiers: ModifierOption[] = [],
    notes: string = ""
): CartItem[] {
    const lineId = makeCartItemId(item.id, selectedModifiers, notes);
    const existingIndex = cart.findIndex((c) => c.id === lineId);
    if (existingIndex >= 0) {
        return cart.map((c, idx) =>
            idx === existingIndex ? { ...c, quantity: c.quantity + 1 } : c
        );
    }
    return [
        ...cart,
        {
            id: lineId,
            menuItem: item,
            quantity: 1,
            selectedModifiers,
            notes,
        },
    ];
}

export function updateQty(cart: CartItem[], lineId: string, delta: number): CartItem[] {
    return cart
        .map((c) =>
            c.id === lineId
                ? { ...c, quantity: Math.max(0, c.quantity + delta) }
                : c
        )
        .filter((c) => c.quantity > 0);
}

export function removeFromCart(cart: CartItem[], lineId: string): CartItem[] {
    return cart.filter((c) => c.id !== lineId);
}

export function cartSubtotal(cart: CartItem[]): number {
    return cart.reduce((sum, c) => sum + lineUnitPrice(c.menuItem, c.selectedModifiers) * c.quantity, 0);
}

export function cartItemCount(cart: CartItem[]): number {
    return cart.reduce((sum, c) => sum + c.quantity, 0);
}

export function cartToOrderItems(cart: CartItem[]): any[] {
    return cart.map((c) => ({
        menu_item_id: c.menuItem.id,
        quantity: c.quantity,
        notes: c.notes || "",
        modifiers: (c.selectedModifiers || []).map((m) => ({
            modifier_option_id: m.id ?? null,
            name: m.name,
            price_delta_cents: m.price_delta_cents || 0,
        })),
    }));
}

