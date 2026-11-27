"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import OwnerShell from "@/components/eleven/OwnerShell";
import { useOwnerFeed, type FeedEvent } from "@/components/eleven/OwnerFeed";
import api from "@/lib/api";

function AlertRow({ title, detail, href }: { title: string; detail?: string; href?: string }) {
  return (
    <li className="owner-glass-panel rounded-2xl p-4">
      <p className="text-[0.9375rem] font-medium leading-6">{title}</p>
      {detail && <p className="mt-1 text-sm text-zinc-400">{detail}</p>}
      {href && (
        <Link href={href} className="mt-2 inline-block text-sm text-[var(--accent)] hover:underline">
          Open
        </Link>
      )}
    </li>
  );
}

function mismatchAlerts(events: FeedEvent[]) {
  return events.filter((e) => e.ai?.status === "mismatch" && e.ai?.note);
}

export default function ElevenAlertsPage() {
  const { data, error } = useOwnerFeed();
  const [rules, setRules] = useState<{ headline?: string; rule_id?: string }[]>([]);

  useEffect(() => {
    api.get("/api/v1/eleven/outcomes/alerts").then((r) => setRules(r.data.custody_gaps ?? r.data.rules ?? [])).catch(() => undefined);
  }, []);
  return (
    <OwnerShell title="Alerts">
      <p className="mb-3 text-xs text-zinc-400">Stock, waste, bills, and photo checks that need your attention.</p>
      {error && <p className="text-sm text-red-300">{error}</p>}
      {!data && !error && <p className="text-sm text-zinc-400">Loading…</p>}
      {data && (
        <ul className="space-y-3">
          {(data.attention?.count ?? 0) > 0 && (
            <AlertRow title={data.attention?.sentence || "Something needs you."} href="/eleven/approvals" />
          )}
          {data.pending
            .filter((item) => (item.action || item.headline || "").trim())
            .map((item) => (
            <AlertRow
              key={`p-${item.kind}-${item.id}`}
              title={item.action || item.headline || "Needs approval"}
              detail={item.headline}
              href="/eleven/approvals"
            />
          ))}
          {(data.bill_reminders ?? []).map((item) => (
            <AlertRow
              key={`b-${item.id}-${item.status}`}
              title={item.headline || item.label || "Bill due"}
              href="/eleven/money"
            />
          ))}
          {rules.map((r) => (
            <AlertRow key={r.rule_id + (r.headline || "")} title={r.headline || "Needs a look"} href="/eleven/approvals" />
          ))}
          {mismatchAlerts(data.events).map((item) => (
            <AlertRow
              key={`ai-${item.kind}-${item.id}`}
              title={item.headline || "Photo check mismatch"}
              detail={item.ai?.note || "Photo check mismatch"}
              href={item.kind === "delivery" ? "/eleven/deliveries" : "/eleven/activity"}
            />
          ))}
          {data.pending.length === 0 &&
            (data.bill_reminders?.length ?? 0) === 0 &&
            mismatchAlerts(data.events).length === 0 &&
            (data.attention?.count ?? 0) === 0 && (
              <li className="owner-glass-panel rounded-2xl p-4 text-sm text-zinc-400">No urgent alerts right now.</li>
            )}
        </ul>
      )}
    </OwnerShell>
  );
}