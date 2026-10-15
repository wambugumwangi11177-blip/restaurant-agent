"use client";
import { Database } from "lucide-react";
import { ago, plural } from "@/lib/owner/format";
import type { Freshness } from "@/lib/owner/types";

/**
 * A restaurant whose figures are a mirror of its point of sale shows none of them until the delivery has been reconciled — a number
 * from a half-delivered feed is worse than no number. Says what is being waited for, from the source's own state.
 */
export default function SourceWaiting({ freshness }: { freshness: Freshness }) {
  const received = freshness.source_records == null ? null : plural(freshness.source_records, "record");
  return (
    <div className="flex gap-3 rounded-xl border border-[hsl(43_76%_57%_/_0.45)] bg-[hsl(43_76%_57%_/_0.1)] p-5">
      <Database className="mt-0.5 shrink-0 text-[var(--v-primary)]" size={22} aria-hidden />
      <div>
        <p className="font-semibold">Waiting for verified restaurant data</p>
        <p role="status" className="mt-1 text-sm text-[var(--v-muted-foreground)]">{freshness.source_notice}</p>
        <p className="mt-3 text-xs text-[var(--v-muted-foreground)]">
          {received ? `${received} received` : "Nothing received yet"}
          {freshness.source_last_received_at ? ` · last ${ago(freshness.source_last_received_at)}` : ""} · {freshness.source_reconciled ? "reconciled" : "not reconciled yet"}
        </p>
        <p className="mt-2 text-xs text-[var(--v-muted-foreground)]">No figure is shown until the delivery has been checked against your till.</p>
      </div>
    </div>
  );
}
