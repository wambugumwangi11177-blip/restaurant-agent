import ChartEmpty, { isEmpty, type ChartStateProps } from "./ChartEmpty";

export type HBar = {
  key: string;
  label: string;
  value: number;
  /** The value as the owner reads it: "KES 61,360" · "12.9 min". */
  valueLabel: string;
  /** Mark a row the owner should look at. */
  flag?: boolean;
  /** A second, quieter line under the label. */
  note?: string;
};

type Props = ChartStateProps & {
  rows: HBar[];
  /** What the whole chart says, for a screen reader. */
  label: string;
  /** Bars are drawn against this; default the largest row. Pass 100 for percentages. */
  max?: number;
};

/** A list of labelled bars on one scale, starting at zero. Rows are HTML so long names wrap and a phone can read them. */
export default function HBars({ rows, label, max, state, reason, day, of }: Props) {
  if (isEmpty(state) || rows.length === 0) return <ChartEmpty state={state ?? "no_data"} reason={reason} day={day} of={of} />;
  const scale = Math.max(max ?? Math.max(...rows.map((r) => r.value)), 1e-9);
  return (
    <ul role="list" aria-label={label} className="space-y-2.5">
      {rows.map((r) => {
        const width = Math.min(100, Math.max(r.value > 0 ? 2 : 0, (r.value / scale) * 100));
        return (
          <li key={r.key} className="text-xs">
            <div className="flex items-baseline justify-between gap-3">
              <span className="min-w-0 truncate font-semibold" title={r.label}>{r.label}</span>
              <span className={`shrink-0 tabular-nums ${r.flag ? "font-bold text-[var(--v-destructive)]" : "text-[var(--v-muted-foreground)]"}`}>{r.valueLabel}</span>
            </div>
            <div aria-hidden className="mt-1 h-2 overflow-hidden rounded-full bg-[var(--v-muted)]">
              <div className="h-full rounded-full" style={{ width: `${width}%`, background: r.flag ? "var(--v-destructive)" : "var(--v-primary)" }} />
            </div>
            {r.note && <p className="mt-0.5 text-[10px] text-[var(--v-muted-foreground)]">{r.note}</p>}
          </li>
        );
      })}
    </ul>
  );
}
