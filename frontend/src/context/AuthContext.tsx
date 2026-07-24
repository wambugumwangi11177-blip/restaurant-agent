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

interface Impersonation {
  session_id: number;
  impersonator_email: string;
}

interface User {
  id: number;
  email: string;
  role: string;
  restaurant_name?: string;
  // Directive 015 — fine-grained tier (owner/manager/supervisor/controller/
  // stockkeeper/kitchen/waiter), or null if not yet assigned. Read fresh from
  // /auth/me on every load rather than cached in a JWT claim, so a role
  // change or the "unassigned" state shows up on the very next page load.
  staff_role: string | null;
  // Real Owner impersonation (not a UI preview): non-null only when the
  // CURRENT request is running as the target of an active session — see
  // backend/routers/staff.py's /impersonate. Read fresh from /auth/me, same
  // reasoning as staff_role above.
  impersonation: Impersonation | null;
  // Informational only — never gates login or access (see backend
  // models.User.is_email_verified docstring). Drives the dashboard's
  // dismissible "verify your email" banner.
  is_email_verified: boolean;
}

interface AuthContextType {
  user: User | null;
  token: string | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, tenantName: string) => Promise<void>;
  logout: () => void;
  isLoading: boolean;
  startImpersonation: (staffId: number) => Promise<string>;
  endImpersonation: () => Promise<void>;
}

// A second, independent localStorage slot for the Owner's own token while
// impersonating. Needed (not just an in-memory variable) so a page refresh
// mid-impersonation doesn't strand the Owner in the target's session with no
// way back — see ImpersonationBanner / dashboard/staff's "View as" button.
const OWNER_TOKEN_KEY = "owner_access_token";

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
    } catch {
      localStorage.removeItem("access_token");
      setToken(null);
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
    localStorage.removeItem(OWNER_TOKEN_KEY);
    setToken(null);
    setUser(null);
  };

  // Owner-only (enforced server-side by require_role(ADMIN) on the
  // /impersonate endpoint) — starts a real, bounded-lifetime session as the
  // target staff member. Stashes the Owner's own token first so it can be
  // restored by endImpersonation() even across a refresh.
  const startImpersonation = async (staffId: number): Promise<string> => {
    const currentToken = localStorage.getItem("access_token");
    if (currentToken) localStorage.setItem(OWNER_TOKEN_KEY, currentToken);

    const res = await api.post(`/staff/${staffId}/impersonate`);
    const impToken = res.data.access_token;
    localStorage.setItem("access_token", impToken);
    setToken(impToken);
    await fetchUser(impToken);
    return impToken;
  };

  // Ends the live session server-side (audit-logged) and restores the
  // Owner's own token client-side. Safe to call even if the end-of-session
  // request fails — the Owner's own token is restored regardless, since a
  // network hiccup shouldn't be able to strand them in the target's account.
  const endImpersonation = async (): Promise<void> => {
    try {
      await api.post("/staff/end-impersonation");
    } catch {
      // Session may have already expired server-side — restoring the
      // Owner's own token below is what actually matters here.
    }
    const ownerToken = localStorage.getItem(OWNER_TOKEN_KEY);
    localStorage.removeItem(OWNER_TOKEN_KEY);
    if (ownerToken) {
      localStorage.setItem("access_token", ownerToken);
      setToken(ownerToken);
      await fetchUser(ownerToken);
    } else {
      logout();
    }
  };

  return (
    <AuthContext.Provider
      value={{ user, token, login, register, logout, isLoading, startImpersonation, endImpersonation }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
}
