"use client";
import { formatSetting } from "@/lib/owner/settings";
import type { Assumption } from "@/lib/owner/types";
import { useSettings } from "./SettingsProvider";

/** "Based on: Lowest share you keep 40% · Change" — the rule a number rests on, said plainly, with a way to change it. */
export default function AssumptionChip({ assumption, className = "" }: { assumption: Assumption; className?: string }) {
  const { fields, openSetting } = useSettings();
  const field = fields?.[assumption.setting];
  const label = assumption.label ?? field?.label ?? assumption.setting;
  const value = field ? formatSetting(field, assumption.value) : String(assumption.value);
  return (
    <span className={`inline-flex flex-wrap items-center gap-x-1.5 text-[10px] text-[var(--v-muted-foreground)] ${className}`} data-testid="based-on">
      <span>Based on: {label} <b className="text-[var(--v-foreground)]">{value}</b></span>
      {field && <button type="button" aria-label={`Change ${label}`} onClick={() => openSetting(assumption.setting)} className="min-h-8 px-1 font-bold text-[var(--v-primary)] underline-offset-2 hover:underline">· Change</button>}
    </span>
  );
}
