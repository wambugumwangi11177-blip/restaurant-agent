/**
 * offlineOrderOutbox.ts
 * ───────────────────────
 * Audit remediation, Tier 4 item 10. POSWorkspace's handleSubmit used to be a
 * single un-queued api.post — an order taken during a connectivity drop was
 * simply lost until a human noticed the error toast and manually retried.
 * This is the missing queue-and-sync layer: a checkout that fails with no
 * network is persisted here instead of shown as a hard failure, then replayed
 * automatically once the browser reports it's back online.
 *
 * IndexedDB, not localStorage — greenfield choice, no existing precedent in
 * this frontend to follow (grepped: none). IndexedDB handles an array of
 * structured order payloads more naturally than JSON-stringifying into a
 * single localStorage key, and isn't capped at ~5MB.
 *
 * Framework-agnostic on purpose (no React) so it can be driven from
 * POSWorkspace's handleSubmit and from a page-load/online-event listener
 * without either depending on the other's lifecycle.
 */

const DB_NAME = "chakula-offline";
const DB_VERSION = 1;
const STORE_NAME = "pending-orders";

export interface PendingOrder {
    localId: string;
    payload: Record<string, unknown>;
    createdAt: number;
    attempts: number;
    lastError?: string;
}

function openDB(): Promise<IDBDatabase> {
    return new Promise((resolve, reject) => {
        if (typeof indexedDB === "undefined") {
            reject(new Error("IndexedDB not available in this environment"));
            return;
        }
        const req = indexedDB.open(DB_NAME, DB_VERSION);
        req.onupgradeneeded = () => {
            const db = req.result;
            if (!db.objectStoreNames.contains(STORE_NAME)) {
                db.createObjectStore(STORE_NAME, { keyPath: "localId" });
            }
        };
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
    });
}

/** True when a failed axios request never reached the server at all — the
 * case this outbox exists for — as distinct from a real server response like
 * 401/422/500 (those have err.response set and should surface as a normal
 * error, not silently queue). */
export function isNetworkFailure(err: unknown): boolean {
    if (!err || typeof err !== "object") return false;
    const e = err as { response?: unknown; request?: unknown; code?: string };
    return !e.response && (Boolean(e.request) || e.code === "ERR_NETWORK");
}

export async function queueOrder(payload: Record<string, unknown>): Promise<PendingOrder> {
    const db = await openDB();
    const order: PendingOrder = {
        localId: `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`,
        payload,
        createdAt: Date.now(),
        attempts: 0,
    };
    await new Promise<void>((resolve, reject) => {
        const tx = db.transaction(STORE_NAME, "readwrite");
        tx.objectStore(STORE_NAME).add(order);
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
    });
    db.close();
    return order;
}

export async function getPendingOrders(): Promise<PendingOrder[]> {
    const db = await openDB();
    const orders = await new Promise<PendingOrder[]>((resolve, reject) => {
        const tx = db.transaction(STORE_NAME, "readonly");
        const req = tx.objectStore(STORE_NAME).getAll();
        req.onsuccess = () => resolve(req.result as PendingOrder[]);
        req.onerror = () => reject(req.error);
    });
    db.close();
    return orders.sort((a, b) => a.createdAt - b.createdAt);
}

export async function removePendingOrder(localId: string): Promise<void> {
    const db = await openDB();
    await new Promise<void>((resolve, reject) => {
        const tx = db.transaction(STORE_NAME, "readwrite");
        tx.objectStore(STORE_NAME).delete(localId);
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
    });
    db.close();
}

/** Drop every queued order (logout on a shared device — queued payloads carry
 * customer names/phones and must not survive into the next user's session). */
export async function clearPendingOrders(): Promise<void> {
    const db = await openDB();
    await new Promise<void>((resolve, reject) => {
        const tx = db.transaction(STORE_NAME, "readwrite");
        tx.objectStore(STORE_NAME).clear();
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
    });
    db.close();
}

async function markAttempt(localId: string, error: string): Promise<void> {
    const db = await openDB();
    await new Promise<void>((resolve, reject) => {
        const tx = db.transaction(STORE_NAME, "readwrite");
        const store = tx.objectStore(STORE_NAME);
        const req = store.get(localId);
        req.onsuccess = () => {
            const existing = req.result as PendingOrder | undefined;
            if (existing) {
                existing.attempts += 1;
                existing.lastError = error;
                store.put(existing);
            }
        };
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
    });
    db.close();
}

/**
 * Replay every queued order via `submit`. Stops at the first failure that's
 * still a network failure (no point burning through the rest of the queue
 * offline) but keeps going past a non-network failure on one order (e.g. a
 * stale menu item id) so the rest of the queue still gets a chance.
 *
 * Module-level mutex: page-load and the `online` event can fire nearly
 * simultaneously (and two POS tabs replay independently of each other via
 * separate page contexts, which is out of scope) — without the guard both
 * replays read the same queue before either deletes, double-submitting
 * every order in it.
 */
let replayInFlight = false;

export async function replayPendingOrders(
    submit: (payload: Record<string, unknown>) => Promise<unknown>
): Promise<{ delivered: number; remaining: number }> {
    if (replayInFlight) return { delivered: 0, remaining: (await getPendingOrders()).length };
    replayInFlight = true;
    try {
        return await _replayLocked(submit);
    } finally {
        replayInFlight = false;
    }
}

async function _replayLocked(
    submit: (payload: Record<string, unknown>) => Promise<unknown>
): Promise<{ delivered: number; remaining: number }> {
    const pending = await getPendingOrders();
    let delivered = 0;

    for (const order of pending) {
        try {
            await submit(order.payload);
            await removePendingOrder(order.localId);
            delivered += 1;
        } catch (err) {
            if (isNetworkFailure(err)) {
                await markAttempt(order.localId, "network unavailable");
                break; // still offline — stop, don't burn through the rest
            }
            await markAttempt(order.localId, err instanceof Error ? err.message : String(err));
            // Non-network failure on this one order — keep going with the rest.
        }
    }

    const remaining = (await getPendingOrders()).length;
    return { delivered, remaining };
}
