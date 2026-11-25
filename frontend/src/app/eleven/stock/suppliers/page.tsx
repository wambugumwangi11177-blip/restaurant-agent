"use client";

import OwnerShell from "@/components/eleven/OwnerShell";
import { useOwnerGet } from "@/hooks/useOwnerV11";

export default function StockSuppliersPage() {
  const { data } = useOwnerGet<{
    rows?: { name: string; lead_days: number; on_time_pct: number; price_jump?: boolean }[];
    has_data?: boolean;
    empty?: string;
  }>("/api/v1/eleven/stock/suppliers", []);
  return (
    <OwnerShell title="Suppliers">
      <ul className="space-y-2 text-sm">
        {(data?.rows ?? []).map((r: { name: string; lead_days: number; on_time_pct: number; price_jump?: boolean }) => (
          <li key={r.name} className="owner-glass-panel px-3 py-2">
            {r.name} · {r.on_time_pct}% on time · {r.lead_days}d lead
            {r.price_jump ? " · price jump flagged" : ""}
          </li>
        ))}
        {!data?.has_data && <p className="text-zinc-400">{data?.empty}</p>}
      </ul>
    </OwnerShell>
  );
}