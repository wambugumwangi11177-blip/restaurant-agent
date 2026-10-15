"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import api from "@/lib/api";
import type { OwnerHome } from "./types";

const REFRESH_MS = 60_000;

export type HomeState = { home: OwnerHome | null; error: boolean; loading: boolean; reload: () => void };

/**
 * GET /api/v1/owner/home for `period`. Keeps what it has while a new period or a refresh loads (the screen never blanks), ignores a
 * slow answer that arrives after a newer request, and re-asks every minute while the tab is visible.
 */
export function useOwnerHome(period: OwnerHome["period"]): HomeState {
  const [home, setHome] = useState<OwnerHome | null>(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);
  const latest = useRef(0);

  const load = useCallback(() => {
    const id = ++latest.current;
    api.get<OwnerHome>("/api/v1/owner/home", { params: { period }, timeout: 30000 })
      .then((r) => { if (id === latest.current) { setHome(r.data); setError(false); } })
      .catch(() => { if (id === latest.current) setError(true); })
      .finally(() => { if (id === latest.current) setLoading(false); });
  }, [period]);

  useEffect(() => {
    // The request is the external synchronisation this effect performs; loading is reset when the period changes.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    load();
    const timer = window.setInterval(() => { if (document.visibilityState === "visible") load(); }, REFRESH_MS);
    return () => { latest.current += 1; window.clearInterval(timer); };
  }, [load]);

  return { home, error, loading, reload: load };
}
