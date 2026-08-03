// POS offline order queue (tech-debt D15). Before this, a failed order POST
// (network drop mid-shift) was just console.error'd — the waiter saw nothing
// and the order was gone. This persists a failed submission to localStorage
// and replays it once connectivity returns, using a client-generated
// idempotency_key (backend/models.py Order.idempotency_key, migration 026) so
// a double-flush can never create a duplicate order.
//
// Hand-rolled rather than pulling in react-query: this is the only offline
// mutation path in the app today (no data-fetching library installed besides
// axios) — a whole library for one queue would be the wrong trade.

import api from "./api";

const STORAGE_KEY = "chakula_offline_orders";

export interface QueuedOrder {
    clientId: string;
    payload: Record<string, unknown>;
    createdAt: number;
}

function readQueue(): QueuedOrder[] {
    if (typeof window === "undefined") return [];
    try {
        const raw = window.localStorage.getItem(STORAGE_KEY);
        return raw ? (JSON.parse(raw) as QueuedOrder[]) : [];
    } catch {
        return [];
    }
}

function writeQueue(queue: QueuedOrder[]): void {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(queue));
}

function newClientId(): string {
    if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
        return crypto.randomUUID();
    }
    // Fallback for environments without crypto.randomUUID (older mobile
    // browsers on a restaurant floor tablet are exactly the case this queue
    // exists for — don't assume a modern API is always present).
    return `local-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function getQueueLength(): number {
    return readQueue().length;
}

/** Persist a failed order submission for later replay. Returns the
 * idempotency key that was stamped onto the payload. */
export function enqueueOrder(payload: Record<string, unknown>): string {
    const clientId = newClientId();
    const queue = readQueue();
    queue.push({
        clientId,
        payload: { ...payload, idempotency_key: clientId },
        createdAt: Date.now(),
    });
    writeQueue(queue);
    return clientId;
}

let flushing = false;

/** Replay queued orders in order. Stops at the first network failure
 * (leaves the rest queued for the next trigger); drops an entry outright on
 * a real 4xx/5xx response, since retrying a validation error won't fix it. */
export async function flushQueue(onFlushed?: (clientId: string) => void): Promise<void> {
    if (flushing || typeof window === "undefined") return;
    if (!window.navigator.onLine) return;
    flushing = true;
    try {
        let queue = readQueue();
        while (queue.length > 0) {
            const next = queue[0];
            try {
                await api.post("/orders/", next.payload);
                queue = queue.slice(1);
                writeQueue(queue);
                onFlushed?.(next.clientId);
            } catch (err) {
                const hasServerResponse =
                    typeof err === "object" && err !== null && "response" in err && (err as { response?: unknown }).response;
                if (hasServerResponse) {
                    queue = queue.slice(1);
                    writeQueue(queue);
                    continue;
                }
                break; // network failure — try the rest later
            }
        }
    } finally {
        flushing = false;
    }
}

/** Wire up online-event + polling flush triggers. Call once per mount;
 * returns a cleanup function. */
export function watchOfflineQueue(onFlushed?: (clientId: string) => void): () => void {
    if (typeof window === "undefined") return () => {};
    const trigger = () => void flushQueue(onFlushed);
    window.addEventListener("online", trigger);
    const interval = window.setInterval(trigger, 30_000);
    trigger(); // flush-on-mount, in case orders were queued last session
    return () => {
        window.removeEventListener("online", trigger);
        window.clearInterval(interval);
    };
}
