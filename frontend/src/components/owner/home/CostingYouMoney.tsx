"use client";
import Link from "next/link";
import { useState } from "react";
import { ChevronRight } from "lucide-react";
import api from "@/lib/api";
import { kes } from "@/lib/owner/format";
import type { CostingYouMoney as Data, DecisionCard } from "@/lib/owner/types";

type Decision = "approved" | "later" | "rejected";

/** Zone 2 — what is costing you money: what is happening now first, then ideas worth the most KES. */
export default function CostingYouMoney({ data }: { data: Data }) {
  const [gone, setGone] = useState<Set<string>>(new Set());
  const cards = data.cards.filter((c) => !gone.has(c.id));
  if (data.cards.length === 0) {
    return (
      <div className="rounded-xl border border-[hsl(150_28%_41%_/_0.24)] bg-[hsl(150_28%_41%_/_0.06)] px-5 py-8 text-center">
        <p className="font-display text-xl font-semibold tracking-[-0.02em]">Nothing is costing you money that we can see</p>
        <p className="mx-auto mt-1.5 max-w-md text-xs text-[var(--v-muted-foreground)]">{data.reason ?? "This is what the checks found, not a promise that every part of the restaurant was looked at."}</p>
      </div>
    );
  }
  return (
    <div className="space-y-3">
      {cards.map((c) => <Card key={c.id} card={c} onDone={() => setGone((g) => new Set(g).add(c.id))} />)}
      {data.more > 0 && (
        <Link href="/os?q=What%20is%20costing%20me%20money%3F" className="inline-flex items-center gap-1 text-xs font-semibold text-[var(--v-primary)]">
          {data.more} more {data.more === 1 ? "idea" : "ideas"} — ask LEVIII <ChevronRight size={12} />
        </Link>
      )}
    </div>
  );
}

function Card({ card, onDone }: { card: DecisionCard; onDone: () => void }) {
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState(false);
  const decide = async (decision: Decision) => {
    if (saving) return;
    setSaving(true);
    setFailed(false);
    try {
      await api.post(`/api/v1/overview/attention/${encodeURIComponent(card.id)}/decision`, { decision });
      onDone();
    } catch {
      setFailed(true);
    } finally {
      setSaving(false);
    }
  };
  return (
    <article className="rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-4 sm:p-5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--v-muted-foreground)]">{card.domain}</span>
        <span className="rounded-full bg-[hsl(42_71%_75%_/_0.55)] px-2 py-0.5 text-[10px] font-bold text-[var(--v-accent-foreground)]">
          {card.kes_month != null ? `about ${kes(card.kes_month)} a month` : "we can't put a number on this yet"}
        </span>
      </div>
      <h3 className="mt-2 text-sm font-bold leading-snug">{card.sentence}</h3>
      <p className="mt-2 text-xs leading-relaxed text-[var(--v-foreground)]">{card.action}</p>
      <details className="mt-2">
        <summary className="cursor-pointer text-[11px] font-semibold text-[var(--v-muted-foreground)]">Why</summary>
        <p className="mt-1 text-xs leading-relaxed text-[var(--v-muted-foreground)]">{card.why}</p>
      </details>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {card.decision && (
          <>
            <button disabled={saving} onClick={() => decide("approved")} className="min-h-10 rounded-lg bg-[var(--v-primary)] px-3 text-[11px] font-bold text-[var(--v-primary-foreground)]">Acknowledge</button>
            <button disabled={saving} onClick={() => decide("later")} className="min-h-10 rounded-lg border border-[var(--v-border)] px-3 text-[11px] font-bold">Remind me in 24h</button>
            <button disabled={saving} onClick={() => decide("rejected")} className="min-h-10 rounded-lg border border-[var(--v-border)] px-3 text-[11px] font-bold">Dismiss</button>
          </>
        )}
        <Link href={`/os?q=${encodeURIComponent(card.sentence)}`} className="inline-flex min-h-10 items-center rounded-lg border border-[hsl(201_47%_29%_/_0.45)] px-3 text-[11px] font-bold text-[var(--v-primary)]">Ask LEVIII about this</Link>
      </div>
      {failed && <p role="alert" className="mt-2 text-xs text-[var(--v-warn)]">Your answer could not be saved. Please try again.</p>}
    </article>
  );
}
