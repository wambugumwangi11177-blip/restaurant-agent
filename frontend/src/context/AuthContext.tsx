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

  const fetchUser = async (accessToken: string) => {
    try {
      const res = await api.get("/api/v1/auth/me", {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      setUser(res.data);
    } catch (err: any) {
      // Only a real 401 means the token itself is invalid — clear it and force
      // a fresh login. Any other failure (network error from an unreachable
      // backend, a 5xx, a timeout) is NOT proof the session is invalid, and
      // must not log the user out — DashboardLayout used to redirect to
      // /login on ANY fetchUser failure, which meant a backend outage always
      // bounced the user to the login screen before any page's own error
      // state (useResource/useAiModule) ever got a chance to render.
      if (err?.response?.status === 401) {
        localStorage.removeItem("access_token");
        setToken(null);
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
