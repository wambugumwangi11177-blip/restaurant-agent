import ChartEmpty, { isEmpty, type ChartStateProps } from "./ChartEmpty";

/** start: a total that opens the chart · minus: something taken away · subtotal / end: where you stand after it. */
export type Step = { key: string; label: string; value: number; kind: "start" | "minus" | "subtotal" | "end"; valueLabel: string };

type Props = ChartStateProps & { steps: Step[]; label: string };

/**
 * Sales down to what you kept, one row each: a bar for what came in, a floating bar for each thing taken away, a bar for where
 * you stand after it. Costs are given as positive amounts and drawn as the part taken off, so a bar never changes direction on
 * the way down; only a loss (what you kept below zero) is drawn to the left of the zero line.
 */
export default function Waterfall({ steps, label, state, reason, day, of }: Props) {
  if (isEmpty(state) || steps.length === 0) return <ChartEmpty state={state ?? "no_data"} reason={reason} day={day} of={of} />;
  // Each bar's place is worked out from the ones before it, without reassigning anything during render.
  const bars = steps.reduce<{ step: Step; lo: number; hi: number; after: number }[]>((acc, s) => {
    const before = acc.length ? acc[acc.length - 1].after : 0;
    const after = s.kind === "minus" ? before - s.value : s.value;
    const [from, to] = s.kind === "minus" ? [after, before] : [0, s.value];
    acc.push({ step: s, lo: Math.min(from, to), hi: Math.max(from, to), after });
    return acc;
  }, []);
  const lo = Math.min(0, ...bars.map((b) => b.lo));
  const hi = Math.max(0, ...bars.map((b) => b.hi));
  const span = hi - lo || 1;
  const pos = (v: number) => ((v - lo) / span) * 100;
  return (
    <ol aria-label={label} className="space-y-2">
      {bars.map(({ step, lo: a, hi: b }) => {
        const total = step.kind === "start" || step.kind === "end";
        const loss = step.kind === "end" && step.value < 0;
        return (
          <li key={step.key} className="grid grid-cols-[7.5rem_1fr_auto] items-center gap-2 text-xs sm:grid-cols-[9rem_1fr_auto]">
            <span className={`leading-tight ${total || step.kind === "subtotal" ? "font-bold" : "text-[var(--v-muted-foreground)]"}`}>{step.label}</span>
            <span aria-hidden className="relative block h-4">
              <span className="absolute inset-y-0 rounded-sm" style={{
                left: `${pos(a)}%`, width: `${Math.max(pos(b) - pos(a), 0.8)}%`,
                background: step.kind === "minus" ? "var(--v-sidebar-primary)" : loss ? "var(--v-destructive)" : step.kind === "end" ? "var(--v-good)" : "var(--v-primary)",
                opacity: step.kind === "subtotal" ? 0.55 : 1,
              }} />
              {lo < 0 && <span className="absolute inset-y-[-2px] w-px bg-[var(--v-border)]" style={{ left: `${pos(0)}%` }} />}
            </span>
            <span className={`tabular-nums ${total ? "font-bold" : ""} ${loss ? "text-[var(--v-destructive)]" : ""}`}>{step.kind === "minus" ? `− ${step.valueLabel}` : step.valueLabel}</span>
          </li>
        );
      })}
    </ol>
  );
}
