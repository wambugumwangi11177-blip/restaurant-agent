"use client";

import { useCallback, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { homeFor } from "@/lib/tenantHome";
import { isLeviiiStoreClient } from "@/lib/nativeStore";
import LockScreen from "@/components/auth/LockScreen";
import SetPinScreen from "@/components/auth/SetPinScreen";
import {
  clearPinUnlock,
  idleLockDue,
  isPinUnlocked,
  markPinUnlocked,
  touchActivity,
} from "@/lib/appLock";

const PUBLIC = ["/login", "/forgot-password", "/reset-password", "/verify-email", "/get"];

export default function AppLockGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() ?? "";
  const router = useRouter();
  const { user, isLoading, logout } = useAuth();
  const [locked, setLocked] = useState(true);
  const [routeHandoff, setRouteHandoff] = useState(false);

  const isPublic = PUBLIC.some((p) => pathname === p || pathname.startsWith(`${p}/`));

  const lock = useCallback(() => {
    clearPinUnlock();
    setLocked(true);
  }, []);

  // Logged-in users must leave / and /login even when the lock overlay blocks {children} (Home never mounts).
  useEffect(() => {
    if (isLoading || !user) return;
    const dest = homeFor(user.tenant_name, user.staff_role);
    if (pathname === dest) return;
    if (pathname === "/login" && isPublic) {
      if (isLeviiiStoreClient()) window.location.replace(dest);
      else router.replace(dest);
      return;
    }
    if (pathname === "/") {
      if (isLeviiiStoreClient()) window.location.replace(dest);
      else router.replace(dest);
    }
  }, [user, isLoading, isPublic, pathname, router]);

  useEffect(() => {
    if (isPublic) {
      setRouteHandoff(false);
      setLocked(false);
      return;
    }
    setRouteHandoff(true);
    const settle = window.setTimeout(() => setRouteHandoff(false), 350);
    return () => window.clearTimeout(settle);
  }, [pathname, isPublic]);

  useEffect(() => {
    if (isPublic || !user) {
      if (isPublic) setLocked(false);
      return;
    }
    if (user.password_auth_valid === false) {
      void logout();
      return;
    }
    if (user.must_change_password || !user.has_pin) {
      setLocked(false);
      return;
    }
    setLocked(!isPinUnlocked() || idleLockDue());
  }, [user, isPublic, logout]);

  useEffect(() => {
    if (isPublic || !user?.has_pin || user.must_change_password) return;

    const onVis = () => {
      if (document.visibilityState === "visible") lock();
    };
    const onAct = () => touchActivity();
    const idleTimer = setInterval(() => {
      if (idleLockDue() && isPinUnlocked()) lock();
    }, 30_000);

    document.addEventListener("visibilitychange", onVis);
    window.addEventListener("pointerdown", onAct, { passive: true });
    window.addEventListener("keydown", onAct);

    return () => {
      document.removeEventListener("visibilitychange", onVis);
      window.removeEventListener("pointerdown", onAct);
      window.removeEventListener("keydown", onAct);
      clearInterval(idleTimer);
    };
  }, [user, isPublic, lock]);

  useEffect(() => {
    if (!locked && user?.has_pin && isPinUnlocked()) touchActivity();
  }, [pathname, locked, user?.has_pin]);

  if (isPublic) return <>{children}</>;

  if (!user && isLoading) {
    return <div className="min-h-dvh bg-[var(--bg)]" aria-busy />;
  }

  if (!user) return <>{children}</>;

  if (isLoading || routeHandoff) {
    return <div className="min-h-dvh bg-[var(--bg)]" role="status" aria-label="Opening" />;
  }

  if (user.password_auth_valid === false) {
    return <div className="min-h-dvh bg-[var(--bg)] text-[var(--text-muted)]" />;
  }

  if (!user.must_change_password && !user.has_pin) {
    return (
      <SetPinScreen
        displayName={user.display_name ?? user.email}
        onDone={() => {
          markPinUnlocked();
          setLocked(false);
        }}
      />
    );
  }

  if (user.has_pin && !user.must_change_password && locked) {
    return (
      <LockScreen displayName={user.display_name ?? user.email} onUnlocked={() => setLocked(false)} />
    );
  }

  return <>{children}</>;
}