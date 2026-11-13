"use client";

import Link from "next/link";
import OwnerShell from "@/components/eleven/OwnerShell";
import OwnerFeed, { useOwnerFeed } from "@/components/eleven/OwnerFeed";
import { GlassCard } from "@/components/eleven/EmptyPanels";

export default function ElevenHomePage() {
  const { data, error, refresh } = useOwnerFeed();
  const count = data?.attention?.count ?? 0;

  return (
    <OwnerShell title="Home">
      {!data && !error && <p className="text-sm text-zinc-400">Loading…</p>}
      {error && <p className="text-sm text-red-300">{error}</p>}
      {data && (
        <div className="space-y-4">
          <Link href="/eleven/approvals" className="owner-glass-panel block rounded-3xl p-4">
            <p className="text-xs uppercase tracking-[0.14em] text-zinc-400">Needs you</p>
            <p className="mt-1 text-lg font-semibold">{data.attention?.sentence}</p>
          </Link>
          <div className="grid grid-cols-1 gap-3">
            {data.cards?.map((card) => (
              <GlassCard key={card.id}>
                <p className="text-xs uppercase tracking-[0.14em] text-zinc-500">{card.title}</p>
                <p className="mt-2 text-base font-medium leading-6">{card.sentence}</p>
                {card.id === "money" && data.till_live && (
                  <p className="mt-3 text-3xl font-semibold tracking-tight">Till live</p>
                )}
              </GlassCard>
            ))}
          </div>
          {(data.unknown_costs ?? []).length > 0 && (
            <GlassCard>
              <p className="text-xs uppercase tracking-[0.14em] text-zinc-500">Still unknown</p>
              <p className="mt-2 text-sm leading-6">
                {(data.unknown_costs?.length ?? 0) === 1
                  ? `${data.unknown_costs?.[0]} has no amount yet.`
                  : `${data.unknown_costs?.join(", ")} have no amount yet.`}
              </p>
            </GlassCard>
          )}
          {(data.recipes_missing ?? 0) > 0 && (
            <GlassCard>
              <p className="text-sm">{data.recipes_missing} dishes still have no recipe.</p>
            </GlassCard>
          )}
          {count > 0 && <p className="text-xs uppercase tracking-[0.14em] text-zinc-500">Waiting at the top of the list</p>}
          <OwnerFeed data={data} onChanged={refresh} />
        </div>
      )}
    </OwnerShell>
  );
}
