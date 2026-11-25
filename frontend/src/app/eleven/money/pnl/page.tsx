"use client";

import { useEffect, useState } from "react";
import OwnerShell from "@/components/eleven/OwnerShell";
import api from "@/lib/api";
import { formatKes } from "@/lib/formatKes";

export default function MonthlyPnlPage() {
  const period = new Date().toISOString().slice(0, 7);
  const [data, setData] = useState<{ lines?: { line: string; kes: number; pct_sales?: number }[]; summary?: string; locked?: boolean } | null>(null);

  useEffect(() => {
    api.get(`/api/v1/eleven/money/pnl/monthly/${period}`).then((r) => setData(r.data));
  }, [period]);

  async function lock() {
    await api.post(`/api/v1/eleven/money/pnl/monthly/${period}/lock`);
    const r = await api.get(`/api/v1/eleven/money/pnl/monthly/${period}`);
    setData(r.data);
  }

  return (
    <OwnerShell title="Full P&L">
      <div className="space-y-3">
        <p className="text-sm text-zinc-400">{data?.summary}</p>
        <ul className="owner-glass-panel divide-y divide-zinc-700/50 text-sm">
          {(data?.lines ?? []).map((row) => (
            <li key={row.line} className="flex justify-between px-4 py-2">
              <span>{row.line}</span>
              <span>
                {formatKes(row.kes)} {row.pct_sales != null ? `· ${row.pct_sales}%` : ""}
              </span>
            </li>
          ))}
        </ul>
        <div className="flex flex-wrap gap-2">
          <a className="owner-oat-highlight px-3 py-2 text-sm" href={`/api/v1/eleven/money/export/monthly/${period}.xlsx`}>
            Download Excel
          </a>
          <a className="owner-oat-highlight px-3 py-2 text-sm" href={`/api/v1/eleven/money/export/monthly/${period}.pdf`}>
            Download PDF
          </a>
          {!data?.locked && (
            <button type="button" className="owner-oat-highlight px-3 py-2 text-sm" onClick={lock}>
              Lock month
            </button>
          )}
        </div>
      </div>
    </OwnerShell>
  );
}