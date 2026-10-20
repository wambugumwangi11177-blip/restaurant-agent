import ChartEmpty, { isEmpty, type ChartStateProps } from "./ChartEmpty";

export type Segment = { key: string; label: string; value: number; color: string };

type Props = ChartStateProps & {
  segments: Segment[];
  /** What the bar says as a whole: "Out of every KES 100 you take". */
  label: string;
  /** How a segment's value reads in the legend; default one decimal. */
  format?: (value: number) => string;
};

/** One bar split into shares. A negative share (a loss) is not drawn as a negative width: it is listed in words. */
export default function StackedBar({ segments, label, format = (v) => v.toFixed(1).replace(/\.0$/, ""), state, reason, day, of }: Props) {
  const drawn = segments.filter((s) => s.value > 0);
  const total = drawn.reduce((t, s) => t + s.value, 0);
  if (isEmpty(state) || total <= 0) return <ChartEmpty state={state ?? "no_data"} reason={reason} day={day} of={of} height={56} />;
  const losses = segments.filter((s) => s.value < 0);
  return (
    <div>
      <div role="img" aria-label={`${label}: ${segments.map((s) => `${s.label} ${format(s.value)}`).join(", ")}`} className="flex h-5 overflow-hidden rounded-md">
        {drawn.map((s) => <div key={s.key} title={`${s.label} ${format(s.value)}`} style={{ width: `${(s.value / total) * 100}%`, background: s.color }} />)}
      </div>
      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px]">
        {segments.map((s) => (
          <li key={s.key} className="flex items-center gap-1.5">
            <span aria-hidden className="h-2.5 w-2.5 rounded-sm" style={{ background: s.value < 0 ? "var(--v-destructive)" : s.color }} />
            <span className="text-[var(--v-muted-foreground)]">{s.label}</span>
            <b className={`tabular-nums ${s.value < 0 ? "text-[var(--v-destructive)]" : ""}`}>{format(s.value)}</b>
          </li>
        ))}
      </ul>
      {losses.length > 0 && <p className="mt-1 text-[11px] text-[var(--v-destructive)]">{losses.map((s) => s.label).join(" and ")} went below zero this period.</p>}
    </div>
  );
}
