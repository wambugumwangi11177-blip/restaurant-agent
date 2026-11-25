"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import OwnerShell from "@/components/eleven/OwnerShell";
import ApprovalCard from "@/components/approvals/ApprovalCard";
import { feedEventLine, useOwnerFeed, type FeedEvent } from "@/components/eleven/OwnerFeed";
import api from "@/lib/api";
import { formatKes } from "@/lib/formatKes";

type Today = {
  has_sales: boolean;
  sales_kes: number;
  tickets: number;
  cash_expected_kes: number;
  empty_sales?: string;
};

type DoneToday = { summary: string | null; empty: string };

type Setup = { steps: { id: string; done: boolean; label: string; href: string }[]; all_done: boolean };

function kesStake(item: FeedEvent): number {
  const cents = (item as { amount_cents?: number }).amount_cents;
  if (typeof cents === "number") return cents;
  return 0;
}

export default function ElevenHomePage() {
  const { data, error, refresh } = useOwnerFeed();
  const [today, setToday] = useState<Today | null>(null);
  const [done, setDone] = useState<DoneToday | null>(null);
  const [setup, setSetup] = useState<Setup | null>(null);

  useEffect(() => {
    const bust = { params: { _: Date.now() }, headers: { "Cache-Control": "no-cache" } };
    Promise.all([
      api.get("/api/v1/eleven/home/today", bust),
      api.get("/api/v1/eleven/home/done-today", bust),
      api.get("/api/v1/eleven/home/setup", bust),
    ]).then(([t, d, s]) => {
      setToday(t.data);
      setDone(d.data);
      setSetup(s.data);
    }).catch(() => undefined);
  }, []);

  const pending = useMemo(() => {
    const items = (data?.pending ?? []).filter((item) => feedEventLine(item));
    return [...items].sort((a, b) => kesStake(b) - kesStake(a));
  }, [data?.pending]);

  const waiting = (data?.events ?? []).filter((e) => e.approval_card_title?.toLowerCase().includes("waiting"));

  const showSetup = setup && !setup.all_done && (!today?.has_sales || pending.length === 0);

  return (
    <OwnerShell title="Home">
      {!data && !error && <p className="text-sm text-zinc-400">Loading…</p>}
      {error && <p className="text-sm text-red-300">{error}</p>}
      {data && (
        <div className="owner-premium-stack">
          <div className="owner-glass-panel flex flex-wrap items-baseline justify-between gap-2 px-4 py-3">
            <TodaySummary today={today} />
          </div>

          <h2 className="owner-label">Needs you</h2>
          {pending.length === 0 ? (
            <p className="text-sm text-zinc-400">
              {data.attention?.sentence || "Nothing needs you right now."}
            </p>
          ) : (
            <ul className="space-y-3">
              {pending.map((item: FeedEvent) => (
                <li key={`${item.kind}-${item.id}`}>
                  <Link href={`/eleven/decisions/${item.kind}/${item.id}`} className="block">
                    {item.approval_card_title ? (
                      <ApprovalCard item={item} />
                    ) : (
                      <DecisionButton item={item} />
                    )}
                  </Link>
                </li>
              ))}
            </ul>
          )}

          {waiting.length > 0 && (
            <>
              <h2 className="owner-label mt-4">Waiting on others</h2>
              <ul className="space-y-2 text-sm text-zinc-300">
                {waiting.slice(0, 8).map((item) => (
                  <li key={`wait-${item.kind}-${item.id}`} className="owner-glass-panel px-3 py-2">
                    {feedEventLine(item)}
                  </li>
                ))}
              </ul>
            </>
          )}

          <h2 className="owner-label mt-4">Done today</h2>
          <p className="text-sm text-zinc-300">{done?.summary ?? done?.empty ?? "—"}</p>

          {showSetup && (
            <>
              <h2 className="owner-label mt-4">Get started</h2>
              <ul className="space-y-2">
                {setup.steps.filter((s) => !s.done).map((step) => (
                  <li key={step.id}>
                    <Link href={step.href} className="owner-oat-highlight block px-3 py-3 text-sm">
                      {step.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </OwnerShell>
  );
}

function TodaySummary({ today }: { today: Today | null }) {
  if (!today) return <p className="text-sm text-zinc-400">Loading today…</p>;
  if (!today.has_sales) {
    return (
      <>
        <p className="text-lg text-zinc-100">Today&apos;s sales: 0 KES</p>
        <p className="text-xs text-zinc-400">{today.empty_sales}</p>
      </>
    );
  }
  return (
    <>
      <p className="text-lg text-zinc-100">
        Today&apos;s sales: {formatKes(today.sales_kes)} · {today.tickets} tickets
      </p>
      <p className="text-sm text-zinc-400">Cash expected at close: {formatKes(today.cash_expected_kes)}</p>
    </>
  );
}

function DecisionButton({ item }: { item: FeedEvent }) {
  return (
    <div className="owner-oat-highlight flex min-h-11 items-center px-3 text-[0.9375rem] text-[var(--text)]">
      {feedEventLine(item)}
    </div>
  );
}