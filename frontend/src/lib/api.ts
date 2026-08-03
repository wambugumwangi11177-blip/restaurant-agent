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
      const retryAfterHeader = error.response.headers?.["retry-after"];
      const retryAfterMs = retryAfterHeader ? Number(retryAfterHeader) * 1000 : 1000;
      await new Promise((resolve) => setTimeout(resolve, Math.min(retryAfterMs, 10_000)));
      return api(config);
    }

    return Promise.reject(error);
  }
);

export default api;
