"use client";

import { useCallback, useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
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
  const { user, isLoading, logout } = useAuth();
  const [locked, setLocked] = useState(true);

  const isPublic = PUBLIC.some((p) => pathname === p || pathname.startsWith(`${p}/`));

  const lock = useCallback(() => {
    clearPinUnlock();
    setLocked(true);
  }, []);

  useEffect(() => {
    if (isPublic || !user) {
      setLocked(false);
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
    return <div className="min-h-dvh bg-[#0a0a0a]" aria-busy />;
  }

  if (!user) return <>{children}</>;

  if (isLoading) {
    return <div className="min-h-dvh bg-[#0a0a0a]" role="status" aria-label="Loading session" />;
  }

  if (user.password_auth_valid === false) {
    return <div className="min-h-dvh bg-[#0a0a0a] text-zinc-400" />;
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