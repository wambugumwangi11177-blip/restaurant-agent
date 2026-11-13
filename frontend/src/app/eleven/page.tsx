"use client";

import Link from "next/link";
import { Package, Trash2, Wallet } from "lucide-react";
import OwnerShell from "@/components/eleven/OwnerShell";
import OwnerFeed, { useOwnerFeed, type FeedCard } from "@/components/eleven/OwnerFeed";

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
  if (card.quiet || !card.figure) {
    return <p className="owner-quiet">{card.title}. {card.sentence}</p>;
  }
  return (
    <article className="owner-glass-panel owner-tile">
      <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-[0.08em] text-zinc-400">
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

  return (
    <OwnerShell title="Home">
      {!data && !error && <p className="text-sm text-zinc-400">Loading…</p>}
      {error && <p className="text-sm text-red-300">{error}</p>}
      {data && (
        <div className="space-y-1">
          <h2 className="owner-label">Needs you</h2>
          {data.pending.length === 0 ? (
            <p className="owner-quiet">{data.attention?.sentence || "Nothing needs you."}</p>
          ) : (
            <ul className="owner-glass-panel mb-3 divide-y divide-white/10 rounded-2xl px-4">
              {data.pending.map((item) => (
                <li key={`${item.kind}-${item.id}`}>
                  <Link href={`/eleven/approvals#${item.kind}-${item.id}`} className="flex min-h-11 items-center text-[0.9375rem]">
                    {item.action || item.headline}
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
