import axios from "axios";
import { getAccessToken, clearAccessToken } from "./tokenStore";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

// Attach JWT token to every request. The token lives in the in-memory token
// store (FE-101) — never in localStorage, which any XSS could read outright.
api.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    const token = getAccessToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

// Handle 401 responses globally
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && typeof window !== "undefined") {
      // Don't redirect when we're already on /login or registering/logging in —
      // the login page fires unauthenticated API calls (trust-stats) and a
      // redirect here used to loop the page into itself forever.
      const isAuthPath =
        window.location.pathname === "/login" ||
        window.location.pathname === "/register" ||
        window.location.pathname === "/order" ||
        (error.config?.url ?? "").includes("/auth/");
      if (!isAuthPath) {
        clearAccessToken();
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  }
);

export default api;
