/**
 * frontend/src/lib/offlineSync.ts
 * ───────────────────────────────────
 * Flushes the offline order queue (lib/offlineQueue.ts) back to the server
 * when connectivity returns, and broadcasts progress via a window event —
 * same pattern as api.ts's SUBSCRIPTION_INACTIVE_EVENT — so any component
 * (the POS page, a sync-status indicator) can show current state without
 * being threaded through a shared React context.
 */

import api, { errorMessage } from "@/lib/api";
import { listPendingOrders, removePendingOrder, markAttempt, type QueuedOrder } from "@/lib/offlineQueue";

export const OFFLINE_SYNC_EVENT = "leviii:offline-sync";

export type SyncEventDetail =
    | { phase: "start"; pending: number }
    | { phase: "order-synced"; clientOrderId: string; remaining: number }
    | { phase: "order-failed"; clientOrderId: string; error: string; remaining: number }
    | { phase: "done"; synced: number; failed: number };

function notify(detail: SyncEventDetail) {
    if (typeof window !== "undefined") {
        window.dispatchEvent(new CustomEvent(OFFLINE_SYNC_EVENT, { detail }));
    }
}

/** True while a network-level failure — not a real server rejection — caused
 * the last enqueue. Used by the POS page to decide "queue offline" vs "show
 * the real error" at submit time. */
export function isNetworkError(err: any): boolean {
    // axios: a response was received (any status) -> the server is reachable
    // and rejected the request for a real reason (validation, 402, etc.) —
    // that must surface normally, not be swallowed into "offline". No
    // response at all is the actual offline/unreachable signal.
    return !err?.response;
}

let syncing = false;

/**
 * Replay every queued order, oldest first, sequentially (not in parallel) —
 * both so the kitchen sees tickets in the order they were actually placed,
 * and so a flaky connection that just came back doesn't get hit with a burst
 * of simultaneous requests the moment it recovers.
 *
 * A queued order that gets a REAL rejection back (not a network failure —
 * e.g. the menu item was deleted while offline) is left in the queue with the
 * error recorded rather than silently dropped. Silently discarding a placed
 * order is a worse failure than one staying visibly stuck; a human needs to
 * look at it, not have it vanish.
 */
export async function syncPendingOrders(): Promise<{ synced: number; failed: number }> {
    if (syncing) return { synced: 0, failed: 0 };
    if (typeof navigator !== "undefined" && navigator.onLine === false) {
        return { synced: 0, failed: 0 };
    }

    syncing = true;
    let synced = 0;
    let failed = 0;
    try {
        const pending = await listPendingOrders();
        if (pending.length === 0) return { synced: 0, failed: 0 };
        notify({ phase: "start", pending: pending.length });

        for (const order of pending) {
            try {
                await api.post("/orders/", { ...order.payload, client_order_id: order.clientOrderId });
                await removePendingOrder(order.clientOrderId);
                synced += 1;
                const remaining = await listPendingOrders();
                notify({ phase: "order-synced", clientOrderId: order.clientOrderId, remaining: remaining.length });
            } catch (err: any) {
                if (isNetworkError(err)) {
                    // Still offline (or connectivity dropped again mid-sync) —
                    // stop here rather than burning through the rest of the
                    // queue against a connection that isn't there; the next
                    // trigger (online event, poll, manual retry) picks up
                    // where this left off.
                    break;
                }
                failed += 1;
                const msg = errorMessage(err, "Server rejected this order");
                await markAttempt(order.clientOrderId, msg);
                const remaining = await listPendingOrders();
                notify({ phase: "order-failed", clientOrderId: order.clientOrderId, error: msg, remaining: remaining.length });
            }
        }
    } finally {
        syncing = false;
        notify({ phase: "done", synced, failed });
    }
    return { synced, failed };
}

let listenersAttached = false;

/**
 * Wire the automatic triggers once per app load: the browser's `online`
 * event, plus a periodic poll as a backstop (the `online` event is not fully
 * reliable across browsers — it can fire before the connection is actually
 * usable, or not fire at all on some mobile networks switching towers).
 */
export function attachAutoSync() {
    if (listenersAttached || typeof window === "undefined") return;
    listenersAttached = true;
    window.addEventListener("online", () => { syncPendingOrders(); });
    setInterval(() => { syncPendingOrders(); }, 30_000);
    // Try once at load — covers the case where the tab was already open and
    // connectivity came back while nothing was listening yet.
    syncPendingOrders();
}
