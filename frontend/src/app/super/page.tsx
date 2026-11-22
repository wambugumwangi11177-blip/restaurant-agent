"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";

type ClientRow = {
  tenant_id: number;
  tenant_name: string;
  restaurant_id: number;
  restaurant_name: string;
  staff_logins: number;
  last_import_at: string | null;
  setup_complete: boolean;
};

type Context = { open: boolean; tenant_name?: string; restaurant_name?: string };

export default function SuperClientsPage() {
  const [clients, setClients] = useState<ClientRow[]>([]);
  const [ctx, setCtx] = useState<Context | null>(null);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    const [list, context] = await Promise.all([
      api.get<ClientRow[]>("/api/v1/super/clients"),
      api.get<Context>("/api/v1/super/context"),
    ]);
    setClients(list.data);
    setCtx(context.data);
  }, []);

  useEffect(() => {
    refresh().catch(() => setError("Could not load clients."));
  }, [refresh]);

  async function openClient(restaurantId: number, tenantName: string) {
    await api.post(`/api/v1/super/open/${restaurantId}`);
    await refresh();
    const dest = tenantName.trim().toLowerCase() === "eleven" ? "/eleven/import" : "/eleven/import";
    window.location.href = dest;
  }

  async function closeClient() {
    await api.post("/api/v1/super/close");
    await refresh();
  }

  return (
    <div className="space-y-6">
      {error && <p className="text-sm text-red-300">{error}</p>}
      {ctx?.open && (
        <section className="rounded-3xl border border-white/15 bg-[#16161a] p-4">
          <p className="text-xs text-zinc-500">Working inside</p>
          <p className="font-semibold">{ctx.tenant_name}</p>
          <p className="text-sm text-zinc-400">{ctx.restaurant_name}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Link href="/eleven/import" className="rounded-full bg-white px-4 py-2 text-sm font-semibold text-black">
              Import
            </Link>
            <Link href="/eleven" className="rounded-full border border-white/20 px-4 py-2 text-sm">
              Owner feed
            </Link>
            <button
              type="button"
              onClick={() => closeClient()}
              className="rounded-full border border-white/20 px-4 py-2 text-sm text-zinc-300"
            >
              Close client
            </button>
          </div>
        </section>
      )}
      <ul className="space-y-3">
        {clients.map((row) => (
          <li key={row.restaurant_id} className="rounded-3xl border border-white/15 bg-[#16161a] p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="font-semibold">{row.tenant_name}</p>
                <p className="text-sm text-zinc-400">{row.restaurant_name}</p>
                <p className="mt-2 text-xs text-zinc-500">
                  {row.staff_logins} login(s)
                  {row.last_import_at ? ` · last import ${new Date(row.last_import_at).toLocaleDateString()}` : " · no import yet"}
                </p>
              </div>
              <button
                type="button"
                onClick={() => openClient(row.restaurant_id, row.tenant_name)}
                className="shrink-0 rounded-full bg-white px-3 py-1.5 text-sm font-semibold text-black"
              >
                Open
              </button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}