"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";

export type OverviewToday = {
  revenue?: { revenue?: number; orders?: number };
  data_provenance?: {
    notice?: string;
    latest_order_at?: string | null;
    source_connection?: { state?: string; reconciled?: boolean };
  };
};

export function useElevenEmpty() {
  const [loading, setLoading] = useState(true);
  const [empty, setEmpty] = useState(true);
  const [provenance, setProvenance] = useState<OverviewToday["data_provenance"]>();

  useEffect(() => {
    api
      .get<OverviewToday>("/api/v1/overview/today?period=today", { timeout: 15000 })
      .then((r) => {
        const orders = r.data.revenue?.orders ?? 0;
        const rev = r.data.revenue?.revenue ?? 0;
        setProvenance(r.data.data_provenance);
        setEmpty(orders === 0 && rev === 0);
      })
      .catch(() => setEmpty(true))
      .finally(() => setLoading(false));
  }, []);

  return { loading, empty, provenance };
}
