// Pure cart math, extracted from dashboard/pos/page.tsx (tech-debt D17/D15) so
// it's testable without rendering the page, and reusable by the offline queue
// (frontend/src/lib/offlineQueue.ts), which needs the same cart -> order-items
// shape the POS submit button builds.

export interface MenuItem {
    id: number;
    name: string;
    price: number;
    category: string;
    description?: string;
    is_available?: boolean;
}

export interface CartItem {
    menuItem: MenuItem;
    quantity: number;
}

export function addToCart(cart: CartItem[], item: MenuItem): CartItem[] {
    const existing = cart.find((c) => c.menuItem.id === item.id);
    if (existing) {
        return cart.map((c) =>
            c.menuItem.id === item.id ? { ...c, quantity: c.quantity + 1 } : c
        );
    }
    return [...cart, { menuItem: item, quantity: 1 }];
}

export function updateQty(cart: CartItem[], itemId: number, delta: number): CartItem[] {
    return cart
        .map((c) =>
            c.menuItem.id === itemId
                ? { ...c, quantity: Math.max(0, c.quantity + delta) }
                : c
        )
        .filter((c) => c.quantity > 0);
}

export function removeFromCart(cart: CartItem[], itemId: number): CartItem[] {
    return cart.filter((c) => c.menuItem.id !== itemId);
}

export function cartSubtotal(cart: CartItem[]): number {
    return cart.reduce((sum, c) => sum + c.menuItem.price * c.quantity, 0);
}

export function cartItemCount(cart: CartItem[]): number {
    return cart.reduce((sum, c) => sum + c.quantity, 0);
}

export function cartToOrderItems(cart: CartItem[]): { menu_item_id: number; quantity: number }[] {
    return cart.map((c) => ({ menu_item_id: c.menuItem.id, quantity: c.quantity }));
}
