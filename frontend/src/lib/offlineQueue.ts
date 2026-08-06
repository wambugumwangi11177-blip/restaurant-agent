/**
 * frontend/src/lib/offlineQueue.ts
 * ───────────────────────────────────
 * IndexedDB-backed order queue for the POS, plus a menu snapshot so the POS
 * has something to sell from if it's opened (or reloaded) with no connection
 * at all.
 *
 * Why this exists: directive 001/006 called the POS "offline-capable" and it
 * never was — `public/sw.js` caches the app shell but explicitly skips `/api`
 * requests, and the POS page kept no local state, so a dropped connection
 * meant no orders could be taken. This is that missing piece.
 *
 * Two object stores in one DB:
 *   - `pending-orders`  — orders placed while offline, waiting to sync.
 *   - `menu-cache`      — the last successfully fetched menu, so the POS can
 *                         still render items to sell if `GET /menu/` itself
 *                         is unreachable (not just the order submission).
 *
 * Every queued order gets a client-generated UUID (`clientOrderId`) sent as
 * `client_order_id` in the create payload. The backend (routers/orders.py)
 * treats a repeat of that id as "already placed" and returns the existing
 * order rather than creating a second one — see migration 026. That's what
 * makes it safe to retry a sync that might have already succeeded server-side
 * (the request landing but its response getting lost is exactly the failure
 * mode a flaky connection produces).
 */

const DB_NAME = "leviii-offline";
const DB_VERSION = 1;
const ORDERS_STORE = "pending-orders";
const MENU_STORE = "menu-cache";

export interface QueuedOrder {
    clientOrderId: string;
    payload: Record<string, unknown>;
    createdAt: number;
    attempts: number;
    lastError?: string;
}

function isSupported(): boolean {
    return typeof window !== "undefined" && "indexedDB" in window;
}

function openDb(): Promise<IDBDatabase> {
    return new Promise((resolve, reject) => {
        const req = indexedDB.open(DB_NAME, DB_VERSION);
        req.onupgradeneeded = () => {
            const db = req.result;
            if (!db.objectStoreNames.contains(ORDERS_STORE)) {
                db.createObjectStore(ORDERS_STORE, { keyPath: "clientOrderId" });
            }
            if (!db.objectStoreNames.contains(MENU_STORE)) {
                db.createObjectStore(MENU_STORE, { keyPath: "id" });
            }
        };
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
    });
}

function uuid(): string {
    // crypto.randomUUID() needs a secure context (https, or localhost) — true
    // for every deployment target here (Vercel is https; local dev is
    // localhost). No polyfill: a POS that can't generate a UUID has bigger
    // problems than offline support.
    return crypto.randomUUID();
}

/** Add an order to the offline queue. Returns the id it was queued under. */
export async function enqueueOrder(payload: Record<string, unknown>): Promise<string> {
    const clientOrderId = uuid();
    const record: QueuedOrder = { clientOrderId, payload, createdAt: Date.now(), attempts: 0 };
    if (!isSupported()) {
        // No IndexedDB (very old browser, or a locked-down webview) — the
        // order can't be queued for later. Surface that as a thrown error so
        // the caller's existing failure UI takes over rather than silently
        // pretending the order was saved.
        throw new Error("Offline queueing is not supported in this browser");
    }
    const db = await openDb();
    await new Promise<void>((resolve, reject) => {
        const tx = db.transaction(ORDERS_STORE, "readwrite");
        tx.objectStore(ORDERS_STORE).put(record);
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
    });
    db.close();
    return clientOrderId;
}

/** All queued orders, oldest first — sync must replay in the order they were
 * placed, so the kitchen sees tickets in the sequence they were actually rung
 * in, not however IndexedDB happens to iterate them. */
export async function listPendingOrders(): Promise<QueuedOrder[]> {
    if (!isSupported()) return [];
    const db = await openDb();
    const orders = await new Promise<QueuedOrder[]>((resolve, reject) => {
        const tx = db.transaction(ORDERS_STORE, "readonly");
        const req = tx.objectStore(ORDERS_STORE).getAll();
        req.onsuccess = () => resolve(req.result as QueuedOrder[]);
        req.onerror = () => reject(req.error);
    });
    db.close();
    return orders.sort((a, b) => a.createdAt - b.createdAt);
}

export async function removePendingOrder(clientOrderId: string): Promise<void> {
    if (!isSupported()) return;
    const db = await openDb();
    await new Promise<void>((resolve, reject) => {
        const tx = db.transaction(ORDERS_STORE, "readwrite");
        tx.objectStore(ORDERS_STORE).delete(clientOrderId);
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
    });
    db.close();
}

export async function markAttempt(clientOrderId: string, error: string): Promise<void> {
    if (!isSupported()) return;
    const db = await openDb();
    await new Promise<void>((resolve, reject) => {
        const tx = db.transaction(ORDERS_STORE, "readwrite");
        const store = tx.objectStore(ORDERS_STORE);
        const getReq = store.get(clientOrderId);
        getReq.onsuccess = () => {
            const record = getReq.result as QueuedOrder | undefined;
            if (record) {
                record.attempts += 1;
                record.lastError = error;
                store.put(record);
            }
        };
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
    });
    db.close();
}

// ── Menu snapshot ─────────────────────────────────────────────────────────

const MENU_CACHE_KEY = "current";

/** Called after every successful `GET /menu/` — keeps the offline fallback fresh. */
export async function cacheMenu(items: unknown[]): Promise<void> {
    if (!isSupported()) return;
    const db = await openDb();
    await new Promise<void>((resolve, reject) => {
        const tx = db.transaction(MENU_STORE, "readwrite");
        tx.objectStore(MENU_STORE).put({ id: MENU_CACHE_KEY, items, cachedAt: Date.now() });
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
    });
    db.close();
}

/** The last cached menu, or null if the POS has never successfully fetched
 * one on this device — a brand-new device that's never been online has
 * nothing to fall back to, which is the correct, unavoidable answer. */
export async function getCachedMenu<T = unknown>(): Promise<{ items: T[]; cachedAt: number } | null> {
    if (!isSupported()) return null;
    const db = await openDb();
    const record = await new Promise<any>((resolve, reject) => {
        const tx = db.transaction(MENU_STORE, "readonly");
        const req = tx.objectStore(MENU_STORE).get(MENU_CACHE_KEY);
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
    });
    db.close();
    return record ? { items: record.items, cachedAt: record.cachedAt } : null;
}
