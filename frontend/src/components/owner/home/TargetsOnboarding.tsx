"use client";
import { useEffect, useState } from "react";
import { Target } from "lucide-react";
import { useSettings } from "@/components/owner/settings/SettingsProvider";
import { HEADLINE_SETTINGS } from "@/lib/owner/settings";
import { readFlag, writeFlag } from "@/lib/owner/storage";

const key = (restaurantId: number) => `owner.targets.later.${restaurantId}`;

/**
 * First run, before any number can be judged: "Your targets" (docs/v2/SPEC.md §3.2). Every figure on Home — what is too high, what is
 * costing money — is measured against the owner's own answers, so a new owner is asked once, with the usual answer filled in. Gone for
 * good once saved; "Not now" hides it for today.
 */
export default function TargetsOnboarding({ restaurantId, chosen }: { restaurantId: number; chosen: boolean }) {
  const { fields, openTargets } = useSettings();
  const [later, setLater] = useState(true);                       // until storage has been read, show nothing rather than flash it
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLater(readFlag(key(restaurantId)) === new Date().toDateString());
  }, [restaurantId]);

  if (chosen || later || !fields) return null;
  const n = HEADLINE_SETTINGS.filter((k) => fields[k]).length;
  return (
    <section aria-labelledby="targets-heading" className="rounded-xl border border-[hsl(43_76%_57%_/_0.5)] bg-[hsl(43_76%_57%_/_0.1)] p-5">
      <div className="flex flex-wrap items-start gap-4">
        <span aria-hidden className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-[var(--v-accent)] text-[var(--v-accent-foreground)]"><Target size={18} /></span>
        <div className="min-w-0 flex-1">
          <h2 id="targets-heading" className="font-display text-xl font-semibold tracking-[-0.03em]">Set your targets</h2>
          <p className="mt-1 max-w-xl text-sm text-[var(--v-muted-foreground)]">
            {n} quick questions, with the answer most restaurants give already filled in. LEVIII judges every number on this page against what you say here — so it tells you what is too high for <i>your</i> restaurant, not for an average one.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <button type="button" onClick={openTargets} className="min-h-11 rounded-lg bg-[var(--v-primary)] px-4 text-sm font-bold text-[var(--v-primary-foreground)]">Set my targets</button>
            <button type="button" onClick={() => { writeFlag(key(restaurantId), new Date().toDateString()); setLater(true); }} className="min-h-11 rounded-lg border border-[var(--v-border)] px-4 text-sm font-semibold">Not now</button>
          </div>
        </div>
      </div>
    </section>
  );
}
