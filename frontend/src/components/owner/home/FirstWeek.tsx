"use client";
import { useEffect, useState } from "react";
import { Compass } from "lucide-react";
import type { AreaKey } from "@/lib/owner/types";
import { readFlag, writeFlag } from "@/lib/owner/storage";

/** The order a new restaurant has something to say in: its permits and targets first, then what it spends, what is in the store, what it sells… */
export const FIRST_WEEK_ORDER: readonly AreaKey[] = ["permits", "money", "store", "sales_dishes", "cash", "staff"];
export const FIRST_WEEK_DAYS = FIRST_WEEK_ORDER.length;

const key = (restaurantId: number) => `owner.firstweek.skipped.${restaurantId}`;

/** Which panels are open on `ageDays` (0 = the day the restaurant joined): one more every day; all of them once the week is over. */
export function unlockedAreas(ageDays: number): ReadonlySet<AreaKey> {
  return new Set(FIRST_WEEK_ORDER.slice(0, Math.max(1, Math.min(FIRST_WEEK_DAYS, ageDays + 1))));
}

/** The panels still shut on `ageDays`, each with the day (1-based) it opens. */
export function lockedAreas(ageDays: number): Partial<Record<AreaKey, number>> {
  const open = unlockedAreas(ageDays);
  return Object.fromEntries(FIRST_WEEK_ORDER.map((k, i) => [k, i + 1] as const).filter(([k]) => !open.has(k)));
}

/**
 * The guided first week is on for a restaurant under a week old whose owner has not skipped it. It says nothing until it has read this
 * restaurant's own choice from storage, so the banner never flashes up on someone who already dismissed it.
 */
export function useFirstWeek(restaurantId: number, ageDays: number): { active: boolean; skip: () => void } {
  const [read, setRead] = useState<{ id: number; skipped: boolean } | null>(null);
  useEffect(() => {
    // Storage is an external system, readable only after mount; the choice is read once per restaurant.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (restaurantId) setRead({ id: restaurantId, skipped: readFlag(key(restaurantId)) === "1" });
  }, [restaurantId]);
  const known = read !== null && read.id === restaurantId;
  return {
    // on while something is still shut: the day the last panel opens the week is over
    active: known && !read.skipped && ageDays >= 0 && ageDays < FIRST_WEEK_DAYS - 1,
    skip: () => { writeFlag(key(restaurantId), "1"); setRead({ id: restaurantId, skipped: true }); },
  };
}

export function FirstWeekBanner({ ageDays, onSkip }: { ageDays: number; onSkip: () => void }) {
  const day = Math.min(ageDays + 1, FIRST_WEEK_DAYS);
  return (
    <aside aria-label="Your first week" className="flex flex-wrap items-center gap-3 rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] px-4 py-3">
      <Compass size={18} aria-hidden className="shrink-0 text-[var(--v-primary)]" />
      <p className="min-w-0 flex-1 text-xs"><b>Your first week · day {day} of {FIRST_WEEK_DAYS}.</b> One more part opens each day, so there is only ever one thing to set up at a time.</p>
      <button type="button" onClick={onSkip} className="min-h-10 rounded-lg border border-[var(--v-border)] px-3 text-[11px] font-bold">Open everything now</button>
    </aside>
  );
}
