"use client";
import { useState } from "react";
import { kes } from "@/lib/owner/format";
import ChartEmpty, { isEmpty, type ChartStateProps } from "./ChartEmpty";

export type ShiftRow = { key: string; when: string; expected: number; counted: number; gap: number; check: boolean };

type Props = ChartStateProps & {
  rows: ShiftRow[];
  label: string;
  /** How many of the newest counts to show before "Show all"; a count to look at is always shown. */
  initial?: number;
};

/** Each cash count against what the till says it should hold. A shift outside what the owner accepts says "Look at this"; a short one is red. */
export default function ShiftTable({ rows, label, initial = 8, state, reason, day, of }: Props) {
  const [all, setAll] = useState(false);
  if (isEmpty(state) || rows.length === 0) return <ChartEmpty state={state ?? "no_data"} reason={reason} day={day} of={of} />;
  const shown = all ? rows : rows.filter((r, i) => i < initial || r.check);
  const hidden = rows.length - shown.length;
  return (
    <div className="overflow-x-auto">
      <table aria-label={label} className="w-full text-left text-xs">
        <thead className="text-[10px] uppercase tracking-[0.1em] text-[var(--v-muted-foreground)]">
          <tr><th scope="col" className="py-1.5 pr-2 font-bold">Shift</th><th scope="col" className="px-1 text-right font-bold sm:px-2">Should hold</th><th scope="col" className="px-1 text-right font-bold sm:px-2">Counted</th><th scope="col" className="pl-2 text-right font-bold">Difference</th></tr>
        </thead>
        <tbody>
          {shown.map((r) => (
            <tr key={r.key} data-check={r.check} className={`border-t border-[var(--v-border)] ${r.check ? "bg-[hsl(4_61%_52%_/_0.07)]" : ""}`}>
              <th scope="row" className="py-2 pr-2 font-semibold">{r.when}{r.check && <span className="ml-2 rounded-full bg-[var(--v-destructive)] px-1.5 py-0.5 text-[9px] font-bold text-white">Look at this</span>}</th>
              <td className="px-1 text-right tabular-nums sm:px-2">{kes(r.expected)}</td>
              <td className="px-1 text-right tabular-nums sm:px-2">{kes(r.counted)}</td>
              <td className={`pl-2 text-right font-semibold tabular-nums ${r.gap < 0 ? "text-[var(--v-destructive)]" : r.gap > 0 ? "text-[var(--v-primary)]" : "text-[var(--v-muted-foreground)]"}`}>{r.gap === 0 ? "Matches" : `${r.gap < 0 ? "Short " : "Over "}${kes(Math.abs(r.gap))}`}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {(hidden > 0 || all) && rows.length > initial && (
        <button type="button" aria-expanded={all} onClick={() => setAll((a) => !a)} className="mt-2 min-h-10 text-[11px] font-bold text-[var(--v-primary)]">
          {all ? "Show fewer" : `Show all ${rows.length} counts`}
        </button>
      )}
    </div>
  );
}
