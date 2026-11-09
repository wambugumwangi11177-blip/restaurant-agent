"use client";

import { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import type { PosReceipt, PosReplay, PosSourceStatus } from "@/lib/posEvidence";
import { GlassCard } from "./EmptyPanels";

function time(value: string | null) {
  if (!value) return "Not recorded";
  const date = new Date(/Z$|[+-]\d\d:\d\d$/.test(value) ? value : value + "Z");
  return new Intl.DateTimeFormat("en-KE", {
    timeZone: "Africa/Nairobi", dateStyle: "medium", timeStyle: "short",
  }).format(date) + " EAT";
}

const actionClass = "min-h-11 rounded-xl border border-white/30 px-4 py-2 text-sm text-white focus-visible:outline-2 focus-visible:outline-white disabled:opacity-70";

export default function PosEvidence() {
  const [source, setSource] = useState<PosSourceStatus | null>(null);
  const [receipts, setReceipts] = useState<PosReceipt[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [status, rows] = await Promise.all([
        api.get<PosSourceStatus>("/api/v1/pos/quicksell/status", { timeout: 15000 }),
        api.get<PosReceipt[]>("/api/v1/pos/quicksell/receipts?limit=20", { timeout: 15000 }),
      ]);
      setSource(status.data);
      setReceipts(rows.data);
    } catch {
      setError("Till evidence could not be loaded. Check your connection and owner access, then retry.");
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  async function replay(id: string) {
    setBusy(id);
    setMessage(null);
    try {
      const result = await api.post<PosReplay>(`/api/v1/pos/quicksell/receipts/${id}/replay`);
      if (result.data.parse_status === "parsed") {
        setMessage(result.data.already_parsed
          ? "This receipt was already parsed. No additional sales were created."
          : `Receipt parsed: ${result.data.orders_inserted} sales added, ${result.data.orders_updated} updated. Sales completeness still needs checking.`);
      } else if (result.data.parse_status === "partial") {
        setMessage(`Receipt partially parsed: ${result.data.orders_inserted} sales added, ${result.data.orders_updated} updated. Other records still need parser review.`);
      } else {
        setMessage("The original receipt is retained. This payload still needs parser review; no successful sale mapping is claimed.");
      }
      await load();
    } catch {
      setMessage("Replay was not confirmed. Refresh the receipt status before retrying.");
    } finally {
      setBusy(null);
    }
  }

  if (loading) return <GlassCard><p role="status">Loading till evidence…</p></GlassCard>;
  if (error) return <GlassCard><p role="alert" className="mb-3 text-sm text-white">{error}</p><button className={actionClass} onClick={() => void load()}>Retry</button></GlassCard>;
  if (!source) return null;
  return (
    <div className="space-y-4 text-white">
      <GlassCard>
        <h2 className="font-semibold">QuickSell receipt evidence</h2>
        <p className="mt-2 text-sm text-zinc-200">{source.durable_inbox_enabled
          ? "Durable receipt capture is enabled."
          : "Durable receipt capture is not enabled on this server. The existing webhook may still be receiving data."}</p>
        <dl className="mt-4 space-y-3 text-sm">
          <div><dt className="text-zinc-300">Source binding</dt><dd>{source.source_bound ? "Bound to this restaurant" : "Not established in the new inbox"}</dd></div>
          <div><dt className="text-zinc-300">Envelopes retained in this inbox</dt><dd className="text-2xl font-semibold">{source.receipts}</dd></div>
          <div><dt className="text-zinc-300">Awaiting parser review or processing</dt><dd>{source.backlog}</dd></div>
          <div><dt className="text-zinc-300">Last authenticated receipt</dt><dd>{time(source.last_receipt_at)}</dd></div>
          <div><dt className="text-zinc-300">Last successful parse</dt><dd>{time(source.last_successful_parse_at)}</dd></div>
          <div><dt className="text-zinc-300">Sales completeness</dt><dd>Not checked</dd></div>
        </dl>
        {source.receipts === 0 && <p className="mt-4 text-sm text-zinc-200">No envelopes recorded in this inbox yet. This does not count earlier mirror records or prove the till has sent nothing.</p>}
        <details className="mt-4 text-sm"><summary className="min-h-11 cursor-pointer py-3 font-semibold">Why these numbers?</summary>
          <p className="mt-2 text-zinc-200">{source.why} Counts cover this restaurant’s retained inbox records across all dates. Backlog adds pending, failed, unrecognized and partially parsed envelopes. Repeat deliveries count as separate receipts; their mapped sales are deduplicated. Earlier mirror history is excluded.</p>
          <p className="mt-2 text-zinc-200">Identical sales without a stable source ID cannot be distinguished reliably from retries. A successful parse does not verify payment methods, dish mapping or complete trading-day coverage.</p>
        </details>
        <button className={actionClass + " mt-3"} onClick={() => void load()}>Refresh evidence</button>
      </GlassCard>
      {message && <p role="status" className="text-sm text-white">{message}</p>}
      {receipts.length > 0 && <GlassCard>
        <h2 className="font-semibold">Latest receipts</h2>
        <p className="mt-1 text-sm text-zinc-200">Showing up to 20 envelopes. Raw customer payloads are not exposed here.</p>
        <ul className="divide-y divide-white/20">
          {receipts.map((receipt) => <li key={receipt.id} className="space-y-2 py-4 text-sm">
            <p className="font-semibold">{time(receipt.received_at)}</p>
            <p>Status: {receipt.status} · Parser attempts: {receipt.attempts}</p>
            {receipt.error_code && <p>Review reason: {receipt.error_code.replaceAll("_", " ")}</p>}
            <details><summary className="min-h-11 cursor-pointer py-3">Receipt reference</summary><code className="block break-all text-xs">{receipt.id}</code></details>
            {receipt.status !== "parsed" && <button className={actionClass} disabled={busy !== null || !source.durable_inbox_enabled} onClick={() => void replay(receipt.id)}>{busy === receipt.id ? "Checking receipt…" : "Retry parser"}</button>}
          </li>)}
        </ul>
      </GlassCard>}
    </div>
  );
}
