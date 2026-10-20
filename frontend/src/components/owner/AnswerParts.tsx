"use client";
/** The two pieces an Ask LEVIII answer and a report section have in common: the rows of figures, and what they rest on. */
import { useSettings } from "@/components/owner/settings/SettingsProvider";
import { rowValue, type AnswerAssumption, type AnswerRow } from "@/lib/owner/ask";

export const LABEL = "text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--v-muted-foreground)]";

/** Label, note and figure, one line each; a row with nothing to show (no figure, no note) is left out. A `why` is the "Why?" detail, where an engine's own words may appear. */
export function Rows({ rows }: { rows: AnswerRow[] }) {
  const shown = rows.filter((r) => r.value != null || r.note);
  if (shown.length === 0) return null;
  return (
    <dl className="divide-y divide-[var(--v-border)] rounded-lg border border-[var(--v-border)] bg-[var(--v-bg)]">
      {shown.map((r, i) => (
        <div key={`${r.key}-${i}`} className="px-3 py-2">
          <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-0.5">
            <dt className="min-w-0 flex-1 basis-40 text-xs">{r.label}{r.note && <span className="mt-0.5 block text-[11px] text-[var(--v-muted-foreground)]">{r.note}</span>}</dt>
            {r.value != null && r.unit !== "text" && <dd className="font-display shrink-0 text-sm font-semibold">{rowValue(r)}</dd>}
          </div>
          {r.why && <details className="text-[11px] text-[var(--v-muted-foreground)]"><summary className="min-h-10 cursor-pointer py-2 font-semibold">Why?</summary><p className="pb-1">{r.why}</p></details>}
        </div>
      ))}
    </dl>
  );
}

/** "What this rests on": the rules an answer used, in words, each with a way to change it where a setting owns the number. */
export function Assumptions({ items }: { items: AnswerAssumption[] }) {
  const { fields, openSetting } = useSettings();
  if (items.length === 0) return null;
  return (
    <div className="space-y-1 border-t border-[var(--v-border)] pt-2 text-[11px] text-[var(--v-muted-foreground)]">
      <p className={LABEL}>What this rests on</p>
      <ul className="list-disc space-y-0.5 pl-4">
        {items.map((a, i) => (
          <li key={i}>{a.text}{a.setting && fields?.[a.setting] && (
            <button type="button" aria-label={`Change ${fields[a.setting].label}`} onClick={() => openSetting(a.setting!)} className="ml-1 min-h-10 px-1 font-bold text-[var(--v-primary)] underline-offset-2 hover:underline">Change</button>
          )}</li>
        ))}
      </ul>
    </div>
  );
}
