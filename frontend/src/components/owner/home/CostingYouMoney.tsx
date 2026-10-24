"use client";
import Link from "next/link";
import { useState } from "react";
import { ChevronRight } from "lucide-react";
import api from "@/lib/api";
import AssumptionChip from "@/components/owner/settings/AssumptionChip";
import { kes } from "@/lib/owner/format";
import type { CardTier, CostingYouMoney as Data, DecisionCard, RankedCard } from "@/lib/owner/types";

type Decision = "approved" | "later" | "rejected";

/** What a card is worth, in words: money going out, money you could make, or an honest "we can't say". */
export function worth(tier: CardTier, kesMonth: number | null): string {
  if (tier === "now") return "happening now";
  if (kesMonth == null) return "we can't put a number on this yet";
  return tier === "loss" ? `costing about ${kes(kesMonth)} a month` : `could earn about ${kes(kesMonth)} a month`;
}

/** Zone 2 — what is costing you money: what is happening now first, then the money going out (most first), then ideas. */
export default function CostingYouMoney({ data }: { data: Data }) {
  const [gone, setGone] = useState<Set<string>>(new Set());
  const [more, setMore] = useState(false);
  const cards = data.cards.filter((c) => !gone.has(c.id));
  if (data.cards.length === 0) {
    return (
      <div className="rounded-xl border border-[hsl(150_28%_41%_/_0.24)] bg-[hsl(150_28%_41%_/_0.06)] px-5 py-8 text-center">
        <p className="font-display text-xl font-semibold tracking-[-0.02em]">Nothing is costing you money that we can see</p>
        <p className="mx-auto mt-1.5 max-w-md text-xs text-[var(--v-muted-foreground)]">{data.reason ?? "This is what the checks found, not a promise that every part of the restaurant was looked at."}</p>
      </div>
    );
  }
  const shown = new Set(data.cards.map((c) => c.id));
  const rest = data.ranked.filter((r) => !shown.has(r.id) && !gone.has(r.id));
  return (
    <div className="space-y-3">
      {cards.map((c) => <Card key={c.id} card={c} onDone={() => setGone((g) => new Set(g).add(c.id))} />)}
      {rest.length > 0 && (
        <div>
          <button type="button" aria-expanded={more} onClick={() => setMore((m) => !m)} className="inline-flex min-h-10 items-center gap-1 text-xs font-semibold text-[var(--v-primary)]">
            {more ? "Show fewer" : `${rest.length} more ${rest.length === 1 ? "idea" : "ideas"}`} <ChevronRight size={12} aria-hidden className={more ? "rotate-90" : ""} />
          </button>
          {more && <ul className="mt-1 divide-y divide-[var(--v-border)] rounded-xl border border-[var(--v-border)] bg-[var(--v-card)]">{rest.map((r) => <MoreRow key={r.id} row={r} />)}</ul>}
        </div>
      )}
    </div>
  );
}

function MoreRow({ row }: { row: RankedCard }) {
  return (
    <li className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5 text-xs">
      <span className="min-w-0 flex-1"><span className="mr-2 text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--v-muted-foreground)]">{row.domain}</span>{row.sentence}</span>
      <span className="font-semibold text-[var(--v-muted-foreground)]">{worth(row.tier, row.kes_month)}</span>
      <Link href={`/os?q=${encodeURIComponent(row.sentence)}`} className="font-bold text-[var(--v-primary)]">Ask LEVIII</Link>
    </li>
  );
}

function ScoreBars({ score }: { score: NonNullable<DecisionCard["score"]> }) {
  const parts = [
    { key: "money", label: "Money", value: score.money, weight: 45 },
    { key: "sure", label: "How sure", value: score.sure, weight: 25 },
    { key: "safe", label: "How safe", value: score.safe, weight: 15 },
    { key: "easy", label: "How easy", value: score.easy, weight: 15 },
  ];
  return (
    <div className="mt-3" aria-label={`Score ${score.total}`}>
      <p className="text-[11px] font-bold">Score {score.total} <span className="font-semibold text-[var(--v-muted-foreground)]">· money 45, how sure 25, how safe 15, how easy 15</span></p>
      <ul className="mt-1.5 space-y-1">
        {parts.map((p) => (
          <li key={p.key} className="grid grid-cols-[4.5rem_1fr_2rem] items-center gap-2 text-[10px]">
            <span className="text-[var(--v-muted-foreground)]">{p.label}</span>
            <span className="h-1.5 overflow-hidden rounded-full bg-[var(--v-muted)]" aria-hidden>
              <span className="block h-full rounded-full bg-[var(--v-primary)]" style={{ width: `${Math.min(100, (p.value / p.weight) * 100)}%` }} />
            </span>
            <span className="text-right tabular-nums">{p.value}</span>
          </li>
        ))}
      </ul>
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
        <span className="rounded-full bg-[hsl(42_71%_75%_/_0.55)] px-2 py-0.5 text-[10px] font-bold text-[var(--v-accent-foreground)]">{worth(card.tier, card.kes_month)}</span>
      </div>
      <h3 className="mt-2 text-sm font-bold leading-snug">{card.sentence}</h3>
      {card.assumption && <AssumptionChip assumption={card.assumption} className="mt-1" />}
      {card.action && card.action !== card.sentence && <p className="mt-2 text-xs leading-relaxed">{card.action}</p>}
      {card.score && <ScoreBars score={card.score} />}
      {(card.why || card.score) && (
        <details className="mt-2">
          <summary className="flex min-h-10 cursor-pointer items-center text-[11px] font-semibold text-[var(--v-muted-foreground)]">See details</summary>
          {card.why && <p className="mt-1 text-xs leading-relaxed text-[var(--v-muted-foreground)]">{card.why}</p>}
        </details>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {card.decision && (
          <>
            <button disabled={saving} onClick={() => decide("approved")} className="min-h-10 rounded-lg bg-[var(--v-primary)] px-3 text-[11px] font-bold text-[var(--v-primary-foreground)]">Approve</button>
            <button disabled={saving} onClick={() => decide("later")} className="min-h-10 rounded-lg border border-[var(--v-border)] px-3 text-[11px] font-bold">Later</button>
            <button disabled={saving} onClick={() => decide("rejected")} className="min-h-10 rounded-lg border border-[var(--v-border)] px-3 text-[11px] font-bold">Dismiss</button>
          </>
        )}
        <Link href={`/os?q=${encodeURIComponent(card.sentence)}`} className="inline-flex min-h-10 items-center rounded-lg border border-[hsl(201_47%_29%_/_0.45)] px-3 text-[11px] font-bold text-[var(--v-primary)]">Ask LEVIII about this</Link>
      </div>
      {failed && <p role="alert" className="mt-2 text-xs text-[var(--v-warn)]">Your answer could not be saved. Please try again.</p>}
    </article>
  );
}
