"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import ApprovalCard from "@/components/approvals/ApprovalCard";

type Req = { kind: string; id: number; label: string; status: string; created_at: string | null };
type InboxItem = { kind: string; id: number; approval_card_title?: string; approval_card_subtitle?: string };

export default function StoreRequestsPage() {
  const [items, setItems] = useState<Req[]>([]);
  const [inbox, setInbox] = useState<InboxItem[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      api.get<{ items: Req[] }>("/api/v1/store/my-requests"),
      api.get<{ pending: InboxItem[] }>("/api/v1/store/approval-inbox"),
    ])
      .then(([mine, waiting]) => {
        setItems(mine.data.items ?? []);
        setInbox(waiting.data.pending ?? []);
      })
      .catch(() => setError("Requests could not be loaded."));
  }, []);

  return (
    <div className="space-y-3">
      <h1 className="text-lg font-semibold">My requests</h1>
      {error && <p className="text-sm text-red-300">{error}</p>}
      {inbox.length > 0 && (
        <ul className="space-y-3">
          {inbox.map((row) => (
            <li key={`${row.kind}-${row.id}`}>
              <ApprovalCard item={row} />
            </li>
          ))}
        </ul>
      )}
      {items.length === 0 && inbox.length === 0 && !error && (
        <p className="text-sm text-zinc-400">Nothing waiting on the owner yet.</p>
      )}
      <ul className="space-y-2">
        {items.map((row) => (
          <li key={`${row.kind}-${row.id}`} className="owner-glass-panel rounded-3xl px-4 py-3 text-sm">
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