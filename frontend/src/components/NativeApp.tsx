"use client";

import { useEffect, useState } from "react";
import { OfflineMark } from "@/components/store/diagrams";
import { shouldOfferStoreUpdate, versionFromUserAgent, type StoreRelease } from "@/lib/storeRelease";
import "@/styles/owner-glass.css";

type CapacitorApp = {
  isNativePlatform?: () => boolean;
  Plugins?: {
    App?: {
      addListener: (event: string, handler: (event: { canGoBack: boolean }) => void) => Promise<{ remove: () => void }> | { remove: () => void };
      minimizeApp?: () => void;
      exitApp?: () => void;
      getInfo?: () => Promise<{ version?: string }>;
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

async function installedVersion(): Promise<string | null> {
  const info = capacitor()?.Plugins?.App?.getInfo?.();
  if (info) {
    try {
      const resolved = await info;
      if (resolved?.version && /^\d+\.\d+\.\d+$/.test(resolved.version)) return resolved.version;
    } catch {
      // The user-agent stamp is the fallback the APK always sends.
    }
  }
  return versionFromUserAgent(navigator.userAgent);
}

export function StoreUpdateBanner({ url }: { url: string }) {
  return (
    <div className="owner-glass-theme px-4 pt-4">
      <div className="owner-glass-panel mx-auto flex max-w-lg flex-col gap-3 rounded-3xl p-4 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm font-semibold">A newer LEVIII Store is ready.</p>
        <a href={url} className="inline-flex min-h-11 items-center justify-center rounded-full bg-white px-4 text-sm font-semibold text-black">
          Download the update
        </a>
      </div>
    </div>
  );
}

export default function NativeApp({ children }: { children: React.ReactNode }) {
  const [offline, setOffline] = useState(false);
  const [updateUrl, setUpdateUrl] = useState<string | null>(null);

  useEffect(() => {
    const native = Boolean(capacitor()?.isNativePlatform?.()) || /LEVIIIStore\/\d+\.\d+\.\d+/.test(navigator.userAgent);
    if (!native) return;
    let live = true;
    (async () => {
      const current = await installedVersion();
      const response = await fetch("/api/app/version", { cache: "no-store" });
      if (!response.ok) return;
      const latest = (await response.json()) as StoreRelease;
      if (!live) return;
      if (shouldOfferStoreUpdate({
        userAgent: navigator.userAgent,
        native: Boolean(capacitor()?.isNativePlatform?.()),
        current,
        latest: latest.version,
        androidUrl: latest.android?.url ?? "",
        androidAvailable: Boolean(latest.android?.available),
      })) {
        setUpdateUrl(latest.android.url);
      }
    })().catch(() => {});
    return () => {
      live = false;
    };
  }, []);

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
  return (
    <>
      {updateUrl && <StoreUpdateBanner url={updateUrl} />}
      {children}
    </>
  );
}
