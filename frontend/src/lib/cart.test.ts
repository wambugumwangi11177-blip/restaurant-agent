import { describe, it, expect } from "vitest";
import {
    addToCart,
    updateQty,
    removeFromCart,
    cartSubtotal,
    cartItemCount,
    cartToOrderItems,
    lineUnitPrice,
    type MenuItem,
    type CartItem,
} from "./cart";

const burger: MenuItem = { id: 1, name: "Burger", price: 50000, category: "Mains" };
const fries: MenuItem = { id: 2, name: "Fries", price: 15000, category: "Sides" };

describe("addToCart", () => {
    it("adds a new item at quantity 1", () => {
        const cart = addToCart([], burger);
        expect(cart.length).toBe(1);
        expect(cart[0].menuItem.name).toBe("Burger");
        expect(cart[0].quantity).toBe(1);
    });

    it("increments quantity for an item already in the cart with same modifiers", () => {
        const cart = addToCart([], burger);
        const result = addToCart(cart, burger);
        expect(result.length).toBe(1);
        expect(result[0].quantity).toBe(2);
    });

    it("creates separate lines for items with different modifiers or notes", () => {
        let cart = addToCart([], burger, [{ name: "Extra Cheese", price_delta_cents: 5000 }]);
        cart = addToCart(cart, burger, [{ name: "Bacon", price_delta_cents: 10000 }]);
        expect(cart.length).toBe(2);
        expect(cartSubtotal(cart)).toBe((50000 + 5000) + (50000 + 10000));
    });
});

describe("updateQty", () => {
    it("increments and decrements quantity", () => {
        let cart = addToCart([], burger);
        const lineId = cart[0].id;
        cart = updateQty(cart, lineId, 1);
        expect(cart[0].quantity).toBe(2);
        cart = updateQty(cart, lineId, -1);
        expect(cart[0].quantity).toBe(1);
    });

    it("floors at 0 and removes the item rather than going negative", () => {
        let cart = addToCart([], burger);
        const lineId = cart[0].id;
        const result = updateQty(cart, lineId, -5);
        expect(result).toEqual([]);
    });
});

describe("removeFromCart", () => {
    it("removes only the targeted item line", () => {
        let cart = addToCart([], burger);
        cart = addToCart(cart, fries);
        const burgerLineId = cart[0].id;
        const result = removeFromCart(cart, burgerLineId);
        expect(result.length).toBe(1);
        expect(result[0].menuItem.id).toBe(2);
    });
});

describe("cartSubtotal / cartItemCount", () => {
    it("sums price * quantity with modifiers across all lines", () => {
        let cart = addToCart([], burger, [{ name: "Cheese", price_delta_cents: 5000 }]);
        cart = addToCart(cart, burger, [{ name: "Cheese", price_delta_cents: 5000 }]); // qty 2 = 2 * 55000 = 110000
        cart = addToCart(cart, fries); // qty 1 = 15000
        expect(cartSubtotal(cart)).toBe(125000);
        expect(cartItemCount(cart)).toBe(3);
    });
});

describe("cartToOrderItems", () => {
    it("maps to the order items shape with modifiers and notes", () => {
        const cart = addToCart([], burger, [{ id: 10, name: "Cheese", price_delta_cents: 5000 }], "Well done");
        const orderItems = cartToOrderItems(cart);
        expect(orderItems).toEqual([
            {
                menu_item_id: 1,
                quantity: 1,
                notes: "Well done",
                modifiers: [{ modifier_option_id: 10, name: "Cheese", price_delta_cents: 5000 }],
            },
        ]);
    });
});

