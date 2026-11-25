"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import OwnerShell from "@/components/eleven/OwnerShell";
import OwnerChartCard from "@/components/eleven/charts/OwnerChartCard";
import { useOwnerGet } from "@/hooks/useOwnerV11";
import api from "@/lib/api";
import { Bar, BarChart, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export default function ElevenStockPage() {
  type Rows = {
    rows?: { name: string; on_hand: number; days_left?: number | null; days_label?: string; status: string }[];
    has_data?: boolean;
    empty?: string;
  };
  const { data: levels } = useOwnerGet<Rows>("/api/v1/eleven/stock/levels", []);
  const { data: reorder } = useOwnerGet<{ rows?: { id: number; item: string; kes: number }[]; has_data?: boolean; empty?: string }>("/api/v1/eleven/stock/reorder", []);
  const { data: missing } = useOwnerGet<{
    issued_kg?: number;
    used_kg?: number;
    gap_kg?: number;
    kes_risk?: number;
    item_name?: string;
    photo_url?: string;
    has_data?: boolean;
    empty?: string;
  }>("/api/v1/eleven/stock/missing", []);
  const { data: trend } = useOwnerGet<{ points?: { day: string; qty: number }[]; has_data?: boolean; empty?: string }>("/api/v1/eleven/stock/use-trend", []);
  const { data: waste } = useOwnerGet<{ bars?: { reason: string; kes: number }[]; has_data?: boolean; empty?: string }>("/api/v1/eleven/stock/waste", []);
  const [missingPhoto, setMissingPhoto] = useState<string | null>(null);

  useEffect(() => {
    if (!missing?.photo_url) {
      setMissingPhoto(null);
      return;
    }
    let active = true;
    api
      .get(missing.photo_url, { responseType: "blob" })
      .then((r) => {
        if (!active) return;
        setMissingPhoto(URL.createObjectURL(r.data));
      })
      .catch(() => active && setMissingPhoto(null));
    return () => {
      active = false;
    };
  }, [missing?.photo_url]);

  return (
    <OwnerShell title="Stock">
      <div className="owner-premium-stack">
        <OwnerChartCard title="Stock levels" caption="Green is OK, amber is low, red is critical." hasData={!!levels?.has_data} emptyHint={levels?.empty ?? "Starts when Jack counts stock."}>
          <ul className="max-h-40 space-y-1 overflow-y-auto text-xs">
            {(levels?.rows ?? []).map((r: { name: string; on_hand: number; days_left?: number | null; days_label?: string; status: string }) => (
              <li key={r.name} className="flex justify-between">
                <span>{r.name}</span>
                <span className={r.status === "red" ? "text-red-300" : ""}>
                  {r.on_hand} · {r.days_label ?? (r.days_left != null ? `${r.days_left}d` : "no use yet")}
                </span>
              </li>
            ))}
          </ul>
        </OwnerChartCard>

        <OwnerChartCard title="Reorder list" caption="Uses per day × supplier lead time." hasData={!!reorder?.has_data} emptyHint={reorder?.empty ?? "Starts when stock runs low."}>
          <ul className="text-xs text-zinc-300">
            {(reorder?.rows ?? []).map((r: { id: number; item: string; kes: number }) => (
              <li key={r.id}>{r.item} — {r.kes.toLocaleString()} KES</li>
            ))}
          </ul>
        </OwnerChartCard>

        <OwnerChartCard title="Missing stock" caption="Issued to kitchen vs used from sales." hasData={!!missing?.has_data} emptyHint={missing?.empty ?? "Starts when kitchen issues and sales move stock."}>
          <p className="text-sm">
            {missing?.item_name ?? "Rice"}: issued {missing?.issued_kg} kg · used {missing?.used_kg} kg
            {missing?.gap_kg ? ` · gap ${missing.gap_kg} kg (~${missing.kes_risk?.toLocaleString()} KES)` : ""}
          </p>
          {missingPhoto && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={missingPhoto} alt="Stock count evidence" className="mt-2 max-h-28 rounded-xl border border-white/10" />
          )}
        </OwnerChartCard>

        <OwnerChartCard title="Use trend" caption="Kitchen issues over the last month." hasData={!!trend?.has_data} emptyHint={trend?.empty ?? "Starts when kitchen uses stock."}>
          <ResponsiveContainer width="100%" height={120}>
            <LineChart data={trend?.points ?? []}>
              <XAxis dataKey="day" hide />
              <YAxis hide />
              <Tooltip />
              <Line type="monotone" dataKey="qty" stroke="#c4b5a8" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </OwnerChartCard>

        <OwnerChartCard title="Waste" caption="Reasons logged by the store." hasData={!!waste?.has_data} emptyHint={waste?.empty ?? "Starts when waste is logged."}>
          <ResponsiveContainer width="100%" height={120}>
            <BarChart data={waste?.bars ?? []}>
              <XAxis dataKey="reason" tick={{ fontSize: 10 }} />
              <YAxis hide />
              <Bar dataKey="kes" fill="#8b7d72" />
            </BarChart>
          </ResponsiveContainer>
        </OwnerChartCard>

        <div className="flex gap-2">
          <Link href="/eleven/stock/suppliers" className="owner-oat-highlight flex-1 px-3 py-3 text-center text-sm">
            Suppliers
          </Link>
          <Link href="/eleven/stock/prep" className="owner-oat-highlight flex-1 px-3 py-3 text-center text-sm">
            Prep
          </Link>
        </div>
      </div>
    </OwnerShell>
  );
}