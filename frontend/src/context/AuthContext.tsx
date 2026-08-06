"use client";

/**
 * AuthContext.tsx — Authentication state management
 *
 * Fixes vs original:
 *   BUG 1 — register was posting to /auth/register (404). Fixed to /api/v1/auth/register.
 *   BUG 6 — login was pointlessly building URLSearchParams then pulling values back out.
 *            Cleaned to send {email, password} JSON directly.
 */

import React, { createContext, useContext, useState, useEffect, ReactNode } from "react";
import api from "@/lib/api";

interface User {
  id: number;
  email: string;
  role: string;
}

interface AuthContextType {
  user: User | null;
  token: string | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, tenantName: string) => Promise<void>;
  logout: () => void;
  isLoading: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const storedToken = localStorage.getItem("access_token");
    if (storedToken) {
      setToken(storedToken);
      fetchUser(storedToken);
    } else {
      setIsLoading(false);
    }
  }, []);

  // Found 2026-08-06 building offline POS support: this unconditionally
  // treated ANY failure of the boot-time "who am I" check as an invalid
  // session — including a network failure, which is exactly what happens on
  // every page reload while offline. The offline POS queue (lib/offlineQueue,
  // the PENDING orders it holds) survives a reload fine — IndexedDB isn't
  // wiped by navigation — but this logged the user straight to /login before
  // they could ever see it, on a device that by definition can't reach
  // /login's own API calls either. The queue was never the weak link; the
  // "am I logged in" bootstrap check was.
  //
  // Fix: only clear the session on a REAL rejection (`err.response` present —
  // the server actually said 401/403, meaning the token itself is bad). A
  // network failure (no response at all) falls back to a locally cached copy
  // of the user object instead, so the session survives being offline. This
  // does not weaken auth: a truly invalid token still gets rejected the
  // moment any request reaches the server — api.ts's own 401 interceptor
  // already forces that logout globally — this only stops a CONNECTIVITY gap
  // from being treated as a REVOKED session.
  const fetchUser = async (accessToken: string) => {
    try {
      const res = await api.get("/api/v1/auth/me", {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      setUser(res.data);
      localStorage.setItem("cached_user", JSON.stringify(res.data));
    } catch (err: any) {
      if (err?.response) {
        // The server actually answered and rejected the token — it's genuinely bad.
        localStorage.removeItem("access_token");
        localStorage.removeItem("cached_user");
        setToken(null);
        setUser(null);
      } else {
        // No response reached us — offline/unreachable, not "logged out".
        // Keep the token, and show whatever we last confirmed about this
        // user so the app renders instead of bouncing to a login screen that
        // can't be reached either.
        const cached = localStorage.getItem("cached_user");
        if (cached) {
          try { setUser(JSON.parse(cached)); } catch { /* corrupt cache — ignore, user stays null */ }
        }
      }
    } finally {
      setIsLoading(false);
    }
  };

  // BUG 6 FIX: removed pointless URLSearchParams construction
  const login = async (email: string, password: string) => {
    const res = await api.post("/api/v1/auth/login", { email, password });
    const accessToken = res.data.access_token;
    localStorage.setItem("access_token", accessToken);
    setToken(accessToken);
    await fetchUser(accessToken);
  };

  // BUG 1 FIX: was /auth/register (404) — corrected to /api/v1/auth/register
  const register = async (email: string, password: string, tenantName: string) => {
    const res = await api.post("/api/v1/auth/register", {
      email,
      password,
      tenant_name: tenantName,
    });
    const accessToken = res.data.access_token;
    localStorage.setItem("access_token", accessToken);
    setToken(accessToken);
    await fetchUser(accessToken);
  };

  const logout = () => {
    localStorage.removeItem("access_token");
    localStorage.removeItem("cached_user");
    setToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, token, login, register, logout, isLoading }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
}
