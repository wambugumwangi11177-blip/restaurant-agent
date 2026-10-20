"use client";
/**
 * Which branch the owner screens are about. Every owner endpoint answers for the user's active restaurant
 * (backend routers/deps.get_restaurant_or_none reads User.active_restaurant_id), so choosing one is POST /restaurants/select
 * and a reload, the same contract as the operations dashboard's RestaurantSwitcher. Renders nothing for a one-branch owner,
 * or when the list cannot be read (a 403 for anyone who is not the owner).
 */
import { useEffect, useState } from "react";
import { Store } from "lucide-react";
import api from "@/lib/api";

interface Branch {
  id: number;
  name: string;
  address: string | null;
  is_active: boolean;
}

/** The branch's name, with the place it is in when the name does not already say it ("Demo Restaurant · Westlands"). */
export function branchLabel(b: Pick<Branch, "name" | "address">): string {
  const place = b.address?.split(",")[0]?.trim();
  return place && !b.name.toLowerCase().includes(place.toLowerCase()) ? `${b.name} · ${place}` : b.name;
}

export default function BranchPicker() {
  const [branches, setBranches] = useState<Branch[]>([]);
  const [switching, setSwitching] = useState(false);

  useEffect(() => {
    api.get("/restaurants/").then((res) => setBranches(res.data)).catch(() => setBranches([]));
  }, []);

  if (branches.length <= 1) return null;
  const active = branches.find((b) => b.is_active) ?? branches[0];

  const choose = async (id: number) => {
    if (id === active.id) return;
    setSwitching(true);
    try {
      await api.post("/restaurants/select", { restaurant_id: id });
      window.location.reload();     // every block on the page was composed for the old branch
    } catch {
      setSwitching(false);
    }
  };

  return (
    <label className="mt-2 inline-flex items-center gap-2 text-[12px] text-[var(--v-muted-foreground)] print:hidden">
      <Store size={14} aria-hidden />
      <span>Branch</span>
      <select value={active.id} disabled={switching} onChange={(e) => choose(Number(e.target.value))}
        className="rounded-lg border border-[var(--v-border)] bg-[var(--v-card)] px-2 py-1.5 text-[13px] font-medium text-[var(--v-foreground)] disabled:opacity-60">
        {branches.map((b) => <option key={b.id} value={b.id}>{branchLabel(b)}</option>)}
      </select>
    </label>
  );
}
