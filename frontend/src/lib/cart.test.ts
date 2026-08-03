import { describe, it, expect } from "vitest";
import {
    addToCart,
    updateQty,
    removeFromCart,
    cartSubtotal,
    cartItemCount,
    cartToOrderItems,
    type MenuItem,
    type CartItem,
} from "./cart";

const burger: MenuItem = { id: 1, name: "Burger", price: 50000, category: "Mains" };
const fries: MenuItem = { id: 2, name: "Fries", price: 15000, category: "Sides" };

describe("addToCart", () => {
    it("adds a new item at quantity 1", () => {
        const cart = addToCart([], burger);
        expect(cart).toEqual([{ menuItem: burger, quantity: 1 }]);
    });

    it("increments quantity for an item already in the cart", () => {
        const cart: CartItem[] = [{ menuItem: burger, quantity: 1 }];
        const result = addToCart(cart, burger);
        expect(result).toEqual([{ menuItem: burger, quantity: 2 }]);
    });

    it("does not mutate the original cart array", () => {
        const cart: CartItem[] = [{ menuItem: burger, quantity: 1 }];
        addToCart(cart, burger);
        expect(cart[0].quantity).toBe(1);
    });
});

describe("updateQty", () => {
    it("increments and decrements quantity", () => {
        let cart: CartItem[] = [{ menuItem: burger, quantity: 1 }];
        cart = updateQty(cart, burger.id, 1);
        expect(cart[0].quantity).toBe(2);
        cart = updateQty(cart, burger.id, -1);
        expect(cart[0].quantity).toBe(1);
    });

    it("floors at 0 and removes the item rather than going negative", () => {
        const cart: CartItem[] = [{ menuItem: burger, quantity: 1 }];
        const result = updateQty(cart, burger.id, -5);
        expect(result).toEqual([]);
    });
});

describe("removeFromCart", () => {
    it("removes only the targeted item", () => {
        const cart: CartItem[] = [
            { menuItem: burger, quantity: 1 },
            { menuItem: fries, quantity: 2 },
        ];
        const result = removeFromCart(cart, burger.id);
        expect(result).toEqual([{ menuItem: fries, quantity: 2 }]);
    });
});

describe("cartSubtotal / cartItemCount", () => {
    const cart: CartItem[] = [
        { menuItem: burger, quantity: 2 },  // 100000
        { menuItem: fries, quantity: 3 },   // 45000
    ];

    it("sums price * quantity across all lines, in cents", () => {
        expect(cartSubtotal(cart)).toBe(145000);
    });

    it("sums quantities across all lines", () => {
        expect(cartItemCount(cart)).toBe(5);
    });

    it("returns 0 for an empty cart", () => {
        expect(cartSubtotal([])).toBe(0);
        expect(cartItemCount([])).toBe(0);
    });
});

describe("cartToOrderItems", () => {
    it("maps to the {menu_item_id, quantity} shape the API expects", () => {
        const cart: CartItem[] = [{ menuItem: burger, quantity: 2 }];
        expect(cartToOrderItems(cart)).toEqual([{ menu_item_id: 1, quantity: 2 }]);
    });
});
