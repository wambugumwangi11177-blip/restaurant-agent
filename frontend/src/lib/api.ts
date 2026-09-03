import axios from "axios";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Fail loudly instead of silently (2026-09-03): when NEXT_PUBLIC_API_URL is
// missing on a Vercel deployment, axios used to fall back to
// http://localhost:8000 — the BROWSER's own machine — and every request died
// with an opaque "Network Error" that looked like a backend outage. This
// surfaces the real cause in the console at runtime.
if (
  typeof window !== "undefined" &&
  process.env.NODE_ENV === "production" &&
  !process.env.NEXT_PUBLIC_API_URL
) {
  console.error(
    "[api] NEXT_PUBLIC_API_URL is NOT set — falling back to http://localhost:8000, " +
      "which will fail from a deployed browser. Fix: Vercel → Project → Settings → " +
      "Environment Variables → NEXT_PUBLIC_API_URL = your Railway backend URL " +
      "(e.g. https://<service>.up.railway.app), then redeploy."
  );
}

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

// Handle 401 responses globally, and retry once on 429 (audit finding §2.7 —
// the backend's rate limiter returns a real 429 with a Retry-After header on
// several routes, but nothing on the frontend ever honored it; a legitimate
// user just saw a raw error).
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401 && typeof window !== "undefined") {
      localStorage.removeItem("access_token");
      window.location.href = "/login";
      return Promise.reject(error);
    }

    const config = error.config;
    if (error.response?.status === 429 && config && !config.__retriedAfter429) {
      config.__retriedAfter429 = true;
      // Retry-After is either delta-seconds or an HTTP-date (RFC 7231 §7.1.3).
      // Number() on the date form yields NaN, which setTimeout coerces to 0 —
      // so we'd retry instantly against a server that just asked us to wait.
      const retryAfterHeader = error.response.headers?.["retry-after"];
      const retryAfterSeconds = Number(retryAfterHeader);
      const retryAfterMs = !retryAfterHeader
        ? 1000
        : Number.isFinite(retryAfterSeconds)
          ? retryAfterSeconds * 1000
          : Math.max(0, Date.parse(retryAfterHeader) - Date.now()) || 1000;
      await new Promise((resolve) => setTimeout(resolve, Math.min(retryAfterMs, 10_000)));
      return api(config);
    }

    return Promise.reject(error);
  }
);

export default api;
