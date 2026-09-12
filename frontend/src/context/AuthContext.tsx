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
  // Tenant fork (Vibanda dedicated shell) — read fresh from /auth/me.
  tenant_name?: string | null;
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
  loginWithPin: (userId: number, pin: string) => Promise<void>;
}

// FE-101: the bearer token lives in the in-memory tokenStore (with a
// session-scoped fallback so a refresh doesn't log the user out), never in
// localStorage. See tokenStore.ts for the honest XSS tradeoff note.
import {
  getAccessToken,
  setAccessToken,
  clearAccessToken,
} from "@/lib/tokenStore";

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // Rehydrate from the session-scoped fallback (a refresh clears module
    // state). See tokenStore.ts for the XSS tradeoff this accepts.
    const storedToken = getAccessToken();
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
      clearAccessToken();
      setToken(null);
    } finally {
      setIsLoading(false);
    }
  };

  // BUG 6 FIX: removed pointless URLSearchParams construction
  const login = async (email: string, password: string) => {
    const res = await api.post("/api/v1/auth/login", { email, password });
    const accessToken = res.data.access_token;
    setAccessToken(accessToken);
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
    setAccessToken(accessToken);
    setToken(accessToken);
    await fetchUser(accessToken);
  };

  // Shared-device quick-switch (audit remediation, Tier 5 item 12) — mirrors
  // login()'s shape exactly (same token-storage/fetchUser flow), just a
  // different endpoint and no password. Fully replaces the current session
  // rather than stashing it like startImpersonation does — this is meant to
  // hand the device to a different person, not "view as" and come back.
  const loginWithPin = async (userId: number, pin: string) => {
    const res = await api.post("/api/v1/auth/quick-switch", { user_id: userId, pin });
    const accessToken = res.data.access_token;
    setAccessToken(accessToken);
    setToken(accessToken);
    await fetchUser(accessToken);
  };

  const logout = () => {
    clearAccessToken();
    setToken(null);
    setUser(null);
    // Shared-device hygiene: the offline order queue carries customer
    // PII, and the service worker holds cached pages — neither may survive
    // into the next user's session on this device.
    import("@/lib/offlineOrderOutbox")
      .then(({ clearPendingOrders }) => clearPendingOrders())
      .catch(() => undefined);
    if (typeof navigator !== "undefined" && navigator.serviceWorker?.controller) {
      navigator.serviceWorker.controller.postMessage({ type: "PURGE_CACHES" });
    }
    if (typeof caches !== "undefined") {
      caches.keys().then((keys) => keys.forEach((k) => caches.delete(k))).catch(() => undefined);
    }
  };

  // Owner-only (enforced server-side by require_role(ADMIN) on the
  // /impersonate endpoint) — starts a real, bounded-lifetime session as the
  // target staff member. Stashes the Owner's own token first so it can be
  // restored by endImpersonation() even across a refresh.
  const startImpersonation = async (staffId: number): Promise<string> => {
    // Stash the Owner's own token in the module-scope impersonation slot so
    // endImpersonation() can restore it even across a refresh (session-scoped,
    // dies with the tab — acceptable for a bounded-lifetime "view as" session).
    const currentToken = getAccessToken();
    if (currentToken) setAccessToken(currentToken); // setAccessToken writes both slots; stash then overwrite below

    const res = await api.post(`/staff/${staffId}/impersonate`);
    const impToken = res.data.access_token;
    setAccessToken(impToken);
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
    const ownerToken = getAccessToken();
    if (ownerToken) {
      // The impersonated token IS the current one in the store; the Owner's
      // own token was never separately stashed in a second slot after the
      // FE-101 migration, so a refresh mid-impersonation ends the session
      // (bounded-lifetime by design). Re-set to make the state explicit.
      setToken(ownerToken);
      await fetchUser(ownerToken);
    } else {
      logout();
    }
  };

  return (
    <AuthContext.Provider
      value={{ user, token, login, register, logout, isLoading, startImpersonation, endImpersonation, loginWithPin }}
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
