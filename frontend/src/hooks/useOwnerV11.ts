"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";

export function useOwnerGet<T = Record<string, unknown>>(path: string, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    setLoading(true);
    api
      .get(path, { params: { _: Date.now() }, headers: { "Cache-Control": "no-cache" } })
      .then((r) => setData(r.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, deps);
  return { data, loading };
}