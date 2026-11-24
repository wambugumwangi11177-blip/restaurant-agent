"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";

type Order = {
  id: number;
  status: string;
  item_name: string;
  quantity: number;
  unit: string;
  supplier_name: string;
  whatsapp_url: string;
  message_draft: string;
};

export default function StoreRestockPage() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function load() {
    const { data } = await api.get<{ orders: Order[] }>("/api/v1/store/restock");
    setOrders(data.orders ?? []);
  }

  useEffect(() => {
    load().catch(() => setError("Restock list could not be loaded."));
  }, []);

  async function markOrdered(id: number) {
    setError("");
    try {
      await api.post("/api/v1/store/restock/ordered", { po_id: id });
      setMessage("Marked as ordered. Receive it when goods arrive.");
      await load();
    } catch {
      setError("Could not mark ordered.");
    }
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-zinc-400">Low stock requests. After approval, send the supplier message, then mark ordered.</p>
      {error && <p className="text-sm text-red-300">{error}</p>}
      {message && <p className="text-sm text-[var(--text)]">{message}</p>}
      {orders.length === 0 ? (
        <p className="owner-glass-panel rounded-3xl p-4 text-sm text-zinc-400">No restock waiting.</p>
      ) : (
        <ul className="space-y-3">
          {orders.map((row) => (
            <li key={row.id} className="owner-glass-panel space-y-2 rounded-3xl p-4 text-sm">
              <p className="font-semibold">
                {row.quantity} {row.unit} {row.item_name}
              </p>
              <p className="text-zinc-400">{row.supplier_name} · {row.status}</p>
              {row.status === "APPROVED" && row.whatsapp_url && (
                <a href={row.whatsapp_url} className="leviii-btn-primary block text-center">
                  Send order to {row.supplier_name}
                </a>
              )}
              {row.status === "APPROVED" && (
                <button type="button" onClick={() => markOrdered(row.id)} className="leviii-btn-ghost w-full py-2">
                  Mark ordered
                </button>
              )}
              {row.status === "PENDING" && <p className="text-xs text-zinc-500">Waiting on approval</p>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}