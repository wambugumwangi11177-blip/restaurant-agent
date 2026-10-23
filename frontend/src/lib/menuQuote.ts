/** What the till charges. `price` is the stored base; `effective_price` is a scheduled price. */
export function sellingPrice(item: { price: number; effective_price?: number | null }): number {
    return item.effective_price ?? item.price;
}

export function isStaleMenuQuote(err: unknown): boolean {
    if (!err || typeof err !== "object" || !("response" in err)) return false;
    const response = (err as { response?: { status?: number; data?: { detail?: unknown } } }).response;
    if (response?.status !== 409) return false;
    const detail = String(response.data?.detail ?? "").toLowerCase();
    return detail.includes("quote") || detail.includes("scheduled price") || detail.includes("reload the menu");
}

type MenuRow = { id: number; price_quote?: string | null };

/** Replace stale quote tokens with the menu's current ones. Lines with no scheduled price drop the token. */
export function repriceOrderPayload(payload: Record<string, unknown>, menu: MenuRow[]): Record<string, unknown> {
    const byId = new Map(menu.map((item) => [item.id, item]));
    const items = Array.isArray(payload.items) ? payload.items as Record<string, unknown>[] : [];
    return {
        ...payload,
        items: items.map((line) => {
            const next = { ...line };
            const item = byId.get(Number(line.menu_item_id));
            if (item?.price_quote) next.price_quote = item.price_quote;
            else delete next.price_quote;
            return next;
        }),
    };
}
