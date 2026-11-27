"use client";

import OwnerShell from "@/components/eleven/OwnerShell";
import { useOwnerGet } from "@/hooks/useOwnerV11";

export default function SettingsConnectionsPage() {
  const { data } = useOwnerGet<{
    till_connected?: boolean;
    till_receipts?: number;
    whatsapp?: boolean;
    accountant_seats?: number;
  }>("/api/v1/eleven/settings/connections", []);

  return (
    <OwnerShell title="Connections">
      <ul className="owner-glass-panel space-y-3 p-5 text-sm">
        <li className="flex justify-between">
          <span>Till / POS</span>
          <span className="text-zinc-400">{data?.till_connected ? `${data.till_receipts} receipts` : "Not connected"}</span>
        </li>
        <li className="flex justify-between">
          <span>WhatsApp owner</span>
          <span className="text-zinc-400">{data?.whatsapp ? "On file" : "Add in restaurant profile"}</span>
        </li>
        <li className="flex justify-between">
          <span>Accountant logins</span>
          <span className="text-zinc-400">{data?.accountant_seats ?? 0}</span>
        </li>
      </ul>
    </OwnerShell>
  );
}