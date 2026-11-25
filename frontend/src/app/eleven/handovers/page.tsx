"use client";

import { useEffect, useState } from "react";
import AuthPhotoThumb from "@/components/AuthPhotoThumb";
import OwnerShell from "@/components/eleven/OwnerShell";
import api from "@/lib/api";

type Handover = {
  id: number;
  created_at: string;
  when_label?: string | null;
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
            <p className="text-zinc-500">{h.when_label || h.created_at}</p>
            <p className="mt-1 text-zinc-300">
              {h.lines.map((l) => `${l.quantity} ${l.unit} ${l.item_name}`).join(", ")}
            </p>
            {h.has_photo && h.photo_path && <AuthPhotoThumb path={h.photo_path} large />}
          </li>
        ))}
        {rows.length === 0 && (
          <li className="owner-glass-panel rounded-2xl p-4 text-sm text-zinc-300">
            No handovers yet. They show here after Jack hands stock to the kitchen with a photo.
          </li>
        )}
      </ul>
    </OwnerShell>
  );
}