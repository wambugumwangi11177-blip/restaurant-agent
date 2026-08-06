import axios from "axios";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

// Attach JWT token to every request
api.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("access_token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

// Name for the window event dispatched below — imported by SubscriptionBanner
// so it doesn't have to guess the string.
export const SUBSCRIPTION_INACTIVE_EVENT = "leviii:subscription-inactive";

// Handle 401 and 402 responses globally.
//
// 401 (bad/expired token) always meant "back to login" and still does.
//
// 402 (added 2026-08-06, alongside billing enforcement on /ai/*) is
// different: the user IS logged in, they're just not paid up. Most pages that
// call /ai/* endpoints swallow errors with `.catch(() => {})` and fall back to
// an empty/loading state, which would make a lapsed subscription look
// indistinguishable from "no data yet" — silently confusing, not a clear
// signal to renew. Rather than editing every one of those call sites, a 402
// anywhere dispatches a window event; SubscriptionBanner (mounted once in the
// dashboard layout) listens and shows a persistent renew prompt. The
// triggering request still rejects normally so per-page handling is
// unaffected — this only adds the global banner on top.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && typeof window !== "undefined") {
      localStorage.removeItem("access_token");
      localStorage.removeItem("cached_user");
      window.location.href = "/login";
    }
    if (error.response?.status === 402 && typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent(SUBSCRIPTION_INACTIVE_EVENT, {
        detail: error.response.data?.detail,
      }));
    }
    return Promise.reject(error);
  }
);

/**
 * Extract a human-readable message from an axios error, regardless of
 * whether the backend's `detail` is a plain string (the FastAPI default —
 * every ordinary 400/404/403) or a structured object.
 *
 * Added 2026-08-06 alongside the billing 402: `require_active_subscription`
 * raises with `detail: {message, status, plan, current_period_end}` so
 * SubscriptionBanner can read the structured fields, but every existing
 * `.catch()` in this app did `e?.response?.data?.detail || fallback` assuming
 * `detail` is always a string — untyped through `catch (e: any)`, so nothing
 * caught it at compile time. The result: any page that fetches an /ai/*
 * endpoint after a subscription lapses tried to render that object directly
 * as a React child and hard-crashed with "Objects are not valid as a React
 * child" instead of showing an error message. Route every one of those call
 * sites through this helper instead of inlining the same unsafe pattern nine
 * times over.
 */
export function errorMessage(err: any, fallback: string): string {
  const detail = err?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && typeof detail.message === "string") return detail.message;
  return err?.message || fallback;
}

export default api;
