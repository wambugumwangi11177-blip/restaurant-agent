"use client";

import OwnerShell from "@/components/eleven/OwnerShell";
import { useOwnerGet } from "@/hooks/useOwnerV11";

export default function SettingsRestaurantPage() {
  const { data } = useOwnerGet<{
    name?: string;
    timezone?: string;
    restock_routing_mode?: string;
    owner_phone?: string;
  }>("/api/v1/eleven/settings/restaurant", []);

  return (
    <OwnerShell title="Restaurant">
      <dl className="owner-glass-panel space-y-3 p-5 text-sm">
        <div className="flex justify-between gap-4">
          <dt className="text-zinc-400">Name</dt>
          <dd>{data?.name ?? "—"}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt className="text-zinc-400">Timezone</dt>
          <dd>{data?.timezone ?? "Africa/Nairobi"}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt className="text-zinc-400">Restock routing</dt>
          <dd className="text-right">{(data?.restock_routing_mode ?? "owner_approves").replace(/_/g, " ")}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt className="text-zinc-400">Owner WhatsApp</dt>
          <dd>{data?.owner_phone || "Not set"}</dd>
        </div>
      </dl>
    </OwnerShell>
  );
}