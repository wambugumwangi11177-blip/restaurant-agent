"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";

type Req = { kind: string; id: number; label: string; status: string; created_at: string | null };

export default function StoreRequestsPage() {
  const [items, setItems] = useState<Req[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .get<{ items: Req[] }>("/api/v1/store/my-requests")
      .then((r) => setItems(r.data.items ?? []))
      .catch(() => setError("Requests could not be loaded."));
  }, []);

  return (
    <div className="space-y-3">
      <h1 className="text-lg font-semibold">My requests</h1>
      {error && <p className="text-sm text-red-300">{error}</p>}
      {items.length === 0 && !error && (
        <p className="text-sm text-zinc-400">Nothing waiting on the owner yet.</p>
      )}
      <ul className="space-y-2">
        {items.map((row) => (
          <li key={`${row.kind}-${row.id}`} className="rounded-3xl border border-white/15 bg-[#16161a] px-4 py-3 text-sm">
            <p className="font-medium">{row.label}</p>
            <p className="text-xs text-zinc-500 capitalize">
              {row.kind} · {row.status.replace(/_/g, " ")}
            </p>
          </li>
        ))}
      </ul>
    </div>
  );
}