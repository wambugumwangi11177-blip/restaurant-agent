"use client";

import { useEffect, useState } from "react";
import OwnerShell from "@/components/eleven/OwnerShell";
import api from "@/lib/api";

type Handover = {
  id: number;
  created_at: string;
  person_name: string;
  chef_name: string;
  has_photo: boolean;
  photo_path?: string | null;
  lines: { item_name: string; quantity: number; unit: string }[];
};

export default function HandoverTimelinePage() {
  const [rows, setRows] = useState<Handover[]>([]);

  useEffect(() => {
    api.get("/api/v1/eleven/outcomes/handovers").then((r) => setRows(r.data.handovers ?? [])).catch(() => undefined);
  }, []);

  return (
    <OwnerShell title="Handovers">
      <p className="mb-3 text-xs text-zinc-400">Store to kitchen with photo — opening and closing each shift.</p>
      <ul className="space-y-3">
        {rows.map((h) => (
          <li key={h.id} className="owner-glass-panel rounded-2xl p-4 text-sm">
            <p className="font-medium">{h.person_name} → {h.chef_name}</p>
            <p className="text-zinc-500">{h.created_at}</p>
            <p className="mt-1 text-zinc-300">
              {h.lines.map((l) => `${l.quantity} ${l.unit} ${l.item_name}`).join(", ")}
            </p>
            {h.has_photo && h.photo_path && (
              <img src={h.photo_path} alt="Handover" className="mt-2 max-h-40 rounded-xl border border-white/10" />
            )}
          </li>
        ))}
        {rows.length === 0 && <li className="text-zinc-400">No handovers yet.</li>}
      </ul>
    </OwnerShell>
  );
}