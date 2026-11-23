"use client";

import Link from "next/link";
import { Package, Trash2, Wallet } from "lucide-react";
import OwnerShell from "@/components/eleven/OwnerShell";
import OwnerFeed, { feedEventLine, useOwnerFeed, type FeedCard, type FeedEvent } from "@/components/eleven/OwnerFeed";

const ICONS = {
  stock: Package,
  waste: Trash2,
  money: Wallet,
} as const;

function recipeLine(count: number) {
  if (count === 1) return "1 dish still has no recipe.";
  return `${count} dishes still have no recipe.`;
}

function Tile({ card }: { card: FeedCard }) {
  const Icon = ICONS[card.id as keyof typeof ICONS] ?? Package;
  const figure = card.figure != null ? String(card.figure).trim() : "";
  const sentence = (card.sentence || "").trim();
  if (card.quiet || !figure) {
    const line = [card.title, sentence].filter(Boolean).join(". ");
    if (!line) return null;
    const tone = card.id === "money" && card.overdue ? "text-red-300" : "text-zinc-400";
    return <p className={`owner-quiet ${tone}`}>{line}</p>;
  }
  if (!sentence && !figure) return null;
  return (
    <article className={`owner-glass-panel owner-tile ${card.id === "money" && card.overdue ? "ring-1 ring-red-400/40" : ""}`}>
      <p className="owner-glass-tag">
        <Icon size={14} strokeWidth={1.75} aria-hidden />
        {card.title}
      </p>
      <p className="owner-figure">{card.figure}</p>
      <p className="text-[0.9375rem] leading-6 text-zinc-200">{card.sentence}</p>
    </article>
  );
}

export default function ElevenHomePage() {
  const { data, error, refresh } = useOwnerFeed();
  const pendingVisible = (data?.pending ?? []).filter((item) => feedEventLine(item));

  return (
    <OwnerShell title="Home">
      {!data && !error && <p className="text-sm text-zinc-400">Loading…</p>}
      {error && <p className="text-sm text-red-300">{error}</p>}
      {data && (
        <div className="owner-premium-stack">
          <h2 className="owner-label">Needs you</h2>
          {pendingVisible.length === 0 ? (
            <div className="owner-oat-highlight mb-3">
              <p className="text-[0.9375rem] leading-6 text-[var(--text)]">
                {data.attention?.count === 0
                  ? "Nothing needs you right now."
                  : data.attention?.sentence || "Nothing needs you right now."}
              </p>
            </div>
          ) : (
            <ul className="owner-oat-highlight mb-3 divide-y divide-white/10 rounded-2xl px-1">
              {pendingVisible.map((item: FeedEvent) => (
                <li key={`${item.kind}-${item.id}`}>
                  <Link
                    href={`/eleven/approvals#${item.kind}-${item.id}`}
                    className="flex min-h-11 items-center px-3 text-[0.9375rem] text-[var(--text)]"
                  >
                    {feedEventLine(item)}
                  </Link>
                </li>
              ))}
            </ul>
          )}
          <div className="space-y-3">
            {data.cards?.filter((card) => card.id !== "approvals").map((card) => (
              <Tile key={card.id} card={card} />
            ))}
          </div>
          {(data.unknown_costs ?? []).length > 0 && (
            <p className="owner-quiet">
              {(data.unknown_costs?.length ?? 0) === 1
                ? `${data.unknown_costs?.[0]} has no amount yet.`
                : `${data.unknown_costs?.join(", ")} have no amount yet.`}
            </p>
          )}
          {(data.recipes_missing ?? 0) > 0 && <p className="owner-quiet">{recipeLine(data.recipes_missing ?? 0)}</p>}
          <div className="pt-2">
            <Link href="/eleven/activity" className="owner-label inline-block">Activity</Link>
            <OwnerFeed data={data} onChanged={refresh} mode="feed" />
          </div>
        </div>
      )}
    </OwnerShell>
  );
}
