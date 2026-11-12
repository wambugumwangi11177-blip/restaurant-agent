"use client";

import { useEffect, useState } from "react";
import { OfflineMark } from "@/components/store/diagrams";
import "@/styles/owner-glass.css";

type CapacitorApp = {
  isNativePlatform?: () => boolean;
  Plugins?: {
    App?: {
      addListener: (event: string, handler: (event: { canGoBack: boolean }) => void) => Promise<{ remove: () => void }> | { remove: () => void };
      minimizeApp?: () => void;
      exitApp?: () => void;
    };
  };
};

function capacitor(): CapacitorApp | null {
  if (typeof window === "undefined") return null;
  return (window as Window & { Capacitor?: CapacitorApp }).Capacitor ?? null;
}

export function OfflineScreen({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="owner-glass-theme flex min-h-screen items-center justify-center px-6">
      <div className="owner-glass-panel w-full max-w-sm rounded-3xl p-6 text-center">
        <OfflineMark />
        <h1 className="mt-3 text-xl font-semibold">No internet</h1>
        <p className="mt-2 text-sm leading-6 text-zinc-300">
          LEVIII Store needs a connection to open the restaurant. Nothing on this phone is the record. Try again when you are back online.
        </p>
        <button
          type="button"
          onClick={onRetry}
          className="mt-5 min-h-11 w-full rounded-full bg-white font-semibold text-black"
        >
          Try again
        </button>
      </div>
    </div>
  );
}

export default function NativeApp({ children }: { children: React.ReactNode }) {
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    const sync = () => setOffline(typeof navigator !== "undefined" && navigator.onLine === false);
    sync();
    window.addEventListener("offline", sync);
    window.addEventListener("online", sync);
    const cap = capacitor();
    let remove: (() => void) | undefined;
    if (cap?.isNativePlatform?.()) {
      document.title = "LEVIII Store";
      const attached = cap.Plugins?.App?.addListener("backButton", ({ canGoBack }) => {
        if (canGoBack) window.history.back();
        else if (cap.Plugins?.App?.minimizeApp) cap.Plugins.App.minimizeApp();
        else cap.Plugins?.App?.exitApp?.();
      });
      if (attached && typeof (attached as Promise<{ remove: () => void }>).then === "function") {
        (attached as Promise<{ remove: () => void }>).then((handle) => {
          remove = () => handle.remove();
        });
      } else if (attached && "remove" in attached) {
        remove = () => attached.remove();
      }
    }
    return () => {
      window.removeEventListener("offline", sync);
      window.removeEventListener("online", sync);
      remove?.();
    };
  }, []);

  if (offline) {
    return <OfflineScreen onRetry={() => window.location.reload()} />;
  }
  return <>{children}</>;
}
