/**
 * frontend/src/lib/useAiModule.ts
 * Shared fetch hook for the AI/analytics endpoints. Extracted from the AI
 * Command Center so ROI, Marketing and Home can reuse the exact same contract.
 *
 * Key subtlety: the backend's _safe_run returns HTTP 200 with
 * {error, available:false} on an internal module failure rather than a non-2xx
 * status — so a 200 with available===false must be surfaced as an error here,
 * not rendered as undefined fields.
 */

import { useEffect, useState } from "react";
import api from "@/lib/api";

export function useAiModule<T>(endpoint: string) {
    const [data, setData] = useState<T | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");

    const fetchData = async () => {
        setLoading(true);
        setError("");
        try {
            const res = await api.get(endpoint);
            if (res.data && res.data.available === false) {
                setError(res.data.error || "This module hit an error analysing your data");
            } else {
                setData(res.data);
            }
        } catch (e: any) {
            setError(e?.response?.data?.detail || e?.message || "Could not load this module");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { fetchData(); }, [endpoint]);

    return { data, loading, error, retry: fetchData };
}

/**
 * Sibling to useAiModule for plain (non-AI) CRUD list/detail fetches — /orders/,
 * /menu/, /reservations/, etc. Same loading/error/retry contract, minus the
 * `available===false` special-case those AI endpoints use (plain resources
 * don't have that convention). `fallback` is what `data` holds before the
 * first successful fetch and on error, so callers can keep rendering a list
 * (e.g. `[]`) without null-checking everywhere.
 *
 * Replaces the previous per-page pattern of raw useState/useEffect +
 * `.catch(() => ({ data: [] }))`, which silently rendered a failed fetch
 * identically to "genuinely zero records" — the failure was invisible.
 */
export function useResource<T>(endpoint: string, fallback: T) {
    const [data, setData] = useState<T>(fallback);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");

    const fetchData = async () => {
        setLoading(true);
        setError("");
        try {
            const res = await api.get(endpoint);
            setData(res.data);
        } catch (e: any) {
            setError(e?.response?.data?.detail || e?.message || "Could not load this");
            setData(fallback);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { fetchData(); }, [endpoint]);

    return { data, loading, error, retry: fetchData };
}
