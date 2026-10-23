import { beforeEach, expect, it } from "vitest";
import { isStaleMenuQuote, repriceOrderPayload, sellingPrice } from "@/lib/menuQuote";
import { clearPendingOrders, getPendingOrders, queueOrder, replayPendingOrders } from "@/lib/offlineOrderOutbox";

beforeEach(async () => {
    await clearPendingOrders();
});

const quoteConflict = {
    response: { status: 409, data: { detail: "Menu quote expired or invalid. Reload the menu and confirm your order." } },
};

it("charges the scheduled price and keeps the base price separate", () => {
    expect(sellingPrice({ price: 50000, effective_price: 45000 })).toBe(45000);
    expect(sellingPrice({ price: 50000, effective_price: null })).toBe(50000);
});

it("replaces an expired quote with the current menu quote and drops one that no longer applies", () => {
    const next = repriceOrderPayload(
        { delivery_channel: "walk_in", items: [{ menu_item_id: 5, quantity: 2, price_quote: "expired" }, { menu_item_id: 6, quantity: 1, price_quote: "expired" }] },
        [{ id: 5, price_quote: "fresh" }, { id: 6 }],
    );
    const items = next.items as { menu_item_id: number; price_quote?: string }[];
    expect(items[0].price_quote).toBe("fresh");
    expect(items[1].price_quote).toBeUndefined();
    expect(isStaleMenuQuote(quoteConflict)).toBe(true);
    expect(isStaleMenuQuote({ response: { status: 422, data: { detail: "no" } } })).toBe(false);
});

it("syncs an offline order after one reprice instead of retrying the stale quote", async () => {
    await queueOrder({ items: [{ menu_item_id: 5, quantity: 1, price_quote: "expired" }], delivery_channel: "walk_in" });
    const submitted: Record<string, unknown>[] = [];
    const result = await replayPendingOrders(async (payload) => {
        submitted.push(payload);
        const quote = (payload.items as { price_quote?: string }[])[0].price_quote;
        if (quote === "expired") throw quoteConflict;
    }, async (payload) => repriceOrderPayload(payload, [{ id: 5, price_quote: "fresh" }]));
    expect(result).toEqual({ delivered: 1, remaining: 0 });
    expect(submitted).toHaveLength(2);
    expect((submitted[1].items as { price_quote?: string }[])[0].price_quote).toBe("fresh");
    expect(await getPendingOrders()).toEqual([]);
});

it("does not loop a quote conflict inside one replay", async () => {
    await queueOrder({ items: [{ menu_item_id: 5, quantity: 1, price_quote: "expired" }] });
    let calls = 0;
    const result = await replayPendingOrders(async () => {
        calls += 1;
        throw quoteConflict;
    }, async (payload) => repriceOrderPayload(payload, [{ id: 5 }]));
    expect(calls).toBe(2);
    expect(result.delivered).toBe(0);
    expect(result.remaining).toBe(1);
    const [left] = await getPendingOrders();
    expect(left.payload).toEqual({ items: [{ menu_item_id: 5, quantity: 1 }] });
    expect(left.attempts).toBe(1);
});
