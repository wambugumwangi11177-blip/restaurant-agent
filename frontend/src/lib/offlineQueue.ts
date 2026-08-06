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

/** Mint an idempotency key. Exported so the POS can stamp it on the *first*
 * attempt: if the server commits but the response is lost in transit, the
 * replay has to carry the same key or the backend sees a new order and
 * creates a duplicate. */
export function newClientId(): string {
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
 * idempotency key that was stamped onto the payload.
 *
 * If the payload already carries an idempotency_key (the caller stamped it
 * before the first attempt, which it should), that key is preserved — minting
 * a fresh one here would be exactly the duplicate-order bug the key prevents. */
export function enqueueOrder(payload: Record<string, unknown>): string {
    const existingKey = typeof payload.idempotency_key === "string" ? payload.idempotency_key : null;
    const clientId = existingKey ?? newClientId();
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

/** Remove one entry by clientId, re-reading storage first.
 *
 * Never write back a pre-await snapshot: enqueueOrder is synchronous and can
 * land while a flush is suspended on the network (same tab: a waiter submits
 * during the flush; shared tablet: a second POS tab, which has its own copy of
 * the `flushing` flag but the same localStorage). A stale slice silently drops
 * whatever was added in that window. */
function removeFromQueue(clientId: string): void {
    writeQueue(readQueue().filter((entry) => entry.clientId !== clientId));
}

/** HTTP status from an axios error, or null for a bare network failure. */
export function errorStatus(err: unknown): number | null {
    if (typeof err !== "object" || err === null || !("response" in err)) return null;
    const response = (err as { response?: { status?: unknown } }).response;
    if (!response || typeof response.status !== "number") return null;
    return response.status;
}

/** True when retrying is pointless: a 4xx the client caused, which will fail
 * identically forever. Everything else — network failure, 5xx, 429 — is
 * transient and must be queued rather than surfaced as a dead end.
 *
 * Exported so the POS's first-attempt path and this module's replay path share
 * one policy. They diverged once, and the result was that a 502 was retried on
 * replay but discarded on first submit. */
export function isTerminalClientError(err: unknown): boolean {
    const status = errorStatus(err);
    return status !== null && status >= 400 && status < 500 && status !== 429;
}

export interface FlushHandlers {
    onFlushed?: (clientId: string) => void;
    /** A queued order was discarded as unsendable. The caller must surface this:
     * the order is gone from storage and the waiter is the only one who can
     * re-enter it. */
    onDropped?: (entry: QueuedOrder, status: number) => void;
}

/** Replay queued orders in order. Stops at the first network failure or
 * retryable server error (leaves the rest queued for the next trigger); drops
 * an entry only on a true client error, since retrying a validation error
 * won't fix it. */
export async function flushQueue(handlers?: FlushHandlers): Promise<void> {
    const { onFlushed, onDropped } = handlers ?? {};
    if (flushing || typeof window === "undefined") return;
    if (!window.navigator.onLine) return;
    flushing = true;
    try {
        // Re-read each iteration so entries queued mid-flush are picked up
        // rather than clobbered. Re-reading means the loop no longer walks a
        // fixed-length snapshot, so `attempted` guarantees termination: each
        // entry is tried at most once per flush, and an entry that somehow
        // survives its own removal can't spin us into an endless POST loop.
        const attempted = new Set<string>();
        let queue = readQueue();
        while (queue.length > 0) {
            const next = queue[0];
            if (attempted.has(next.clientId)) break;
            attempted.add(next.clientId);
            try {
                await api.post("/orders/", next.payload);
                removeFromQueue(next.clientId);
                onFlushed?.(next.clientId);
            } catch (err) {
                // 4xx (except 429) is the client's fault and will fail forever —
                // drop it, but tell the caller so the loss is visible. 5xx and
                // 429 are transient: a Railway restart or a DB timeout must not
                // delete an order the idempotency key made safely retryable.
                if (isTerminalClientError(err)) {
                    removeFromQueue(next.clientId);
                    onDropped?.(next, errorStatus(err) as number);
                    queue = readQueue();
                    continue;
                }
                break; // network failure, 5xx, or 429 — try the rest later
            }
            queue = readQueue();
        }
    } finally {
        flushing = false;
    }
}

/** Wire up online-event + polling flush triggers. Call once per mount;
 * returns a cleanup function. */
export function watchOfflineQueue(handlers?: FlushHandlers): () => void {
    if (typeof window === "undefined") return () => {};
    const trigger = () => void flushQueue(handlers);
    window.addEventListener("online", trigger);
    const interval = window.setInterval(trigger, 30_000);
    trigger(); // flush-on-mount, in case orders were queued last session
    return () => {
        window.removeEventListener("online", trigger);
        window.clearInterval(interval);
    };
}
