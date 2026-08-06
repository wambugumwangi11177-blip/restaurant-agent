/**
 * POS offline queue (tech-debt D15). The queue exists so a failed order is
 * never lost, so every test here is about one thing: an order that was really
 * placed must survive until the server has it.
 *
 * Covers the three ways it previously leaked orders — dropping retryable
 * server errors, clobbering entries queued mid-flush, and minting a fresh
 * idempotency key on replay (which turns one order into two).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("./api", () => ({
    default: { post: vi.fn() },
}));

import api from "./api";
import {
    enqueueOrder,
    flushQueue,
    getQueueLength,
    newClientId,
    isTerminalClientError,
} from "./offlineQueue";

const STORAGE_KEY = "chakula_offline_orders";

function axiosErrorWithStatus(status: number) {
    return { response: { status, data: {} } };
}

function readRaw() {
    return JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "[]");
}

beforeEach(() => {
    localStorage.clear();
    vi.mocked(api.post).mockReset();
    vi.stubGlobal("navigator", { onLine: true });
});

describe("enqueueOrder", () => {
    it("preserves an idempotency key the caller already stamped", () => {
        // The POS stamps the key before its first attempt; minting a new one
        // here would make the replay look like a brand-new order.
        enqueueOrder({ items: [], idempotency_key: "stamped-by-pos" });
        const [entry] = readRaw();
        expect(entry.payload.idempotency_key).toBe("stamped-by-pos");
        expect(entry.clientId).toBe("stamped-by-pos");
    });

    it("mints a key when the payload has none", () => {
        enqueueOrder({ items: [] });
        const [entry] = readRaw();
        expect(entry.payload.idempotency_key).toBeTruthy();
        expect(entry.payload.idempotency_key).toBe(entry.clientId);
    });
});

describe("flushQueue error handling", () => {
    it("keeps the order queued on a 5xx", async () => {
        enqueueOrder({ items: [], idempotency_key: "k1" });
        vi.mocked(api.post).mockRejectedValue(axiosErrorWithStatus(502));

        await flushQueue();

        // A Railway restart must not delete an order the key made retryable.
        expect(getQueueLength()).toBe(1);
    });

    it("keeps the order queued on a 429", async () => {
        enqueueOrder({ items: [], idempotency_key: "k2" });
        vi.mocked(api.post).mockRejectedValue(axiosErrorWithStatus(429));

        await flushQueue();

        expect(getQueueLength()).toBe(1);
    });

    it("drops the order on a 4xx that will never succeed", async () => {
        enqueueOrder({ items: [], idempotency_key: "k3" });
        vi.mocked(api.post).mockRejectedValue(axiosErrorWithStatus(422));

        await flushQueue();

        expect(getQueueLength()).toBe(0);
    });

    it("reports a dropped order so the loss isn't silent", async () => {
        enqueueOrder({ items: [], idempotency_key: "k3b" });
        vi.mocked(api.post).mockRejectedValue(axiosErrorWithStatus(400));

        const onDropped = vi.fn();
        const onFlushed = vi.fn();
        await flushQueue({ onFlushed, onDropped });

        // Only the waiter can re-enter a discarded order, so the caller has to
        // hear about it.
        expect(onDropped).toHaveBeenCalledTimes(1);
        expect(onDropped.mock.calls[0][0].clientId).toBe("k3b");
        expect(onDropped.mock.calls[0][1]).toBe(400);
        expect(onFlushed).not.toHaveBeenCalled();
    });

    it("does not report a drop when the failure is retryable", async () => {
        enqueueOrder({ items: [], idempotency_key: "k3c" });
        vi.mocked(api.post).mockRejectedValue(axiosErrorWithStatus(503));

        const onDropped = vi.fn();
        await flushQueue({ onDropped });

        expect(onDropped).not.toHaveBeenCalled();
        expect(getQueueLength()).toBe(1);
    });

    it("keeps the order queued on a bare network failure", async () => {
        enqueueOrder({ items: [], idempotency_key: "k4" });
        vi.mocked(api.post).mockRejectedValue(new Error("Network Error"));

        await flushQueue();

        expect(getQueueLength()).toBe(1);
    });

    it("retries the 5xx entry successfully on a later flush", async () => {
        enqueueOrder({ items: [], idempotency_key: "k5" });
        vi.mocked(api.post).mockRejectedValueOnce(axiosErrorWithStatus(503));
        await flushQueue();
        expect(getQueueLength()).toBe(1);

        vi.mocked(api.post).mockResolvedValueOnce({ data: { id: 1 } });
        await flushQueue();
        expect(getQueueLength()).toBe(0);
    });
});

describe("flushQueue concurrency", () => {
    it("does not clobber an order enqueued while a flush is in flight", async () => {
        enqueueOrder({ items: ["A"], idempotency_key: "A" });

        // Resolve the in-flight POST only after a second order has been queued —
        // this is the waiter submitting during a flush, or a second POS tab
        // writing to the same localStorage.
        vi.mocked(api.post).mockImplementationOnce(async () => {
            enqueueOrder({ items: ["B"], idempotency_key: "B" });
            return { data: { id: 1 } };
        });
        vi.mocked(api.post).mockResolvedValue({ data: { id: 2 } });

        await flushQueue();

        // Both must have been sent; neither may be silently dropped.
        expect(vi.mocked(api.post)).toHaveBeenCalledTimes(2);
        const sentKeys = vi.mocked(api.post).mock.calls.map(
            (c) => (c[1] as { idempotency_key: string }).idempotency_key
        );
        expect(sentKeys).toEqual(["A", "B"]);
        expect(getQueueLength()).toBe(0);
    });

    it("removes the flushed entry by id, not by position", async () => {
        enqueueOrder({ items: ["A"], idempotency_key: "A" });

        vi.mocked(api.post).mockImplementationOnce(async () => {
            enqueueOrder({ items: ["B"], idempotency_key: "B" });
            return { data: { id: 1 } };
        });
        // B fails with a network error, so it should remain queued.
        vi.mocked(api.post).mockRejectedValue(new Error("Network Error"));

        await flushQueue();

        const remaining = readRaw();
        expect(remaining).toHaveLength(1);
        expect(remaining[0].clientId).toBe("B");
    });
});

describe("newClientId", () => {
    it("returns a unique value each call", () => {
        expect(newClientId()).not.toBe(newClientId());
    });
});

describe("isTerminalClientError", () => {
    // The POS's first-attempt path and the replay path both branch on this.
    // They diverged once — a 502 was retried on replay but discarded on submit —
    // so the policy lives here and is asserted in one place.
    it("treats a true 4xx as terminal", () => {
        expect(isTerminalClientError(axiosErrorWithStatus(400))).toBe(true);
        expect(isTerminalClientError(axiosErrorWithStatus(422))).toBe(true);
    });

    it("treats 5xx, 429, and network failures as retryable", () => {
        expect(isTerminalClientError(axiosErrorWithStatus(500))).toBe(false);
        expect(isTerminalClientError(axiosErrorWithStatus(502))).toBe(false);
        expect(isTerminalClientError(axiosErrorWithStatus(429))).toBe(false);
        expect(isTerminalClientError(new Error("Network Error"))).toBe(false);
    });
});
