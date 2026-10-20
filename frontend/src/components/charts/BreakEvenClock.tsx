import { kes } from "@/lib/owner/format";
import ChartEmpty, { isEmpty, type ChartStateProps } from "./ChartEmpty";

type Props = ChartStateProps & {
  /** What the day has to sell to cover its costs, and what it has sold so far. */
  breakEven: number;
  soldSoFar: number;
  /** "12:31 pm" when sales crossed the line, else null. */
  coveredAt: string | null;
  label: string;
};

const R = 42;
const C = 2 * Math.PI * R;

/** A ring that fills as today's sales climb to what the day has to cover; it turns green, and says when, the moment it does. */
export default function BreakEvenClock({ breakEven, soldSoFar, coveredAt, label, state, reason, day, of }: Props) {
  if (isEmpty(state) || breakEven <= 0) return <ChartEmpty state={state ?? "no_data"} reason={reason} day={day} of={of} height={140} />;
  const share = Math.min(1, soldSoFar / breakEven);
  const covered = coveredAt != null;
  const toGo = Math.max(breakEven - soldSoFar, 0);
  return (
    <figure className="flex items-center gap-4">
      <svg role="img" aria-label={`${label}: ${covered ? `covered at ${coveredAt}` : `${kes(toGo)} to go`}`} viewBox="0 0 100 100" className="h-28 w-28 shrink-0 -rotate-90">
        <circle cx="50" cy="50" r={R} fill="none" stroke="var(--v-muted)" strokeWidth="10" />
        <circle cx="50" cy="50" r={R} fill="none" stroke={covered ? "var(--v-good)" : "var(--v-primary)"} strokeWidth="10" strokeLinecap="round"
          strokeDasharray={`${share * C} ${C}`} />
      </svg>
      <figcaption>
        <p className="font-display text-xl font-semibold tracking-[-0.03em]">{covered ? `Covered at ${coveredAt}` : `${kes(toGo)} to go`}</p>
        <p className="mt-0.5 text-xs text-[var(--v-muted-foreground)]">{kes(soldSoFar)} sold of the {kes(breakEven)} today has to cover.</p>
      </figcaption>
    </figure>
  );
}
