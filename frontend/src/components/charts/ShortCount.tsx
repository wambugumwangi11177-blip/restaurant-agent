import { kes } from "@/lib/owner/format";
import type { BlockState } from "@/lib/owner/types";
import ChartEmpty from "./ChartEmpty";

type Props = {
  expected: number;
  counted: number;
  gap: number;
  trick?: string | null;
  windowLabel?: string;
  state?: BlockState;
  reason?: string | null;
  example?: boolean;
};

/** The till against the count, with the gap a short drawer is built to catch. */
export default function ShortCount({ expected, counted, gap, trick, windowLabel = "last 14 days", state, reason, example = false }: Props) {
  if (!example && (state === "no_data" || state === "unavailable" || expected == null)) {
    return <ChartEmpty state={state ?? "no_data"} reason={reason || "A short count draws here once a drawer is counted."} height={120} />;
  }
  const top = Math.max(expected, counted, 1);
  const h = (v: number) => Math.max(4, (v / top) * 70);
  const short = gap < 0;
  return (
    <figure>
      <svg role="img" aria-label={`Cash count, ${windowLabel}. Till ${kes(expected)}, counted ${kes(counted)}.`} viewBox="0 0 320 120" className="w-full">
        <rect x="70" y={100 - h(expected)} width="36" height={h(expected)} fill="var(--chart-line, #60a5fa)" />
        <rect x="150" y={100 - h(counted)} width="36" height={h(counted)} fill={short ? "var(--danger, #f87171)" : "var(--chart-bar, #e0b15a)"} />
        <text x="88" y="112" textAnchor="middle" fontSize="8" fill="var(--v-muted-foreground)">Till</text>
        <text x="168" y="112" textAnchor="middle" fontSize="8" fill="var(--v-muted-foreground)">Counted</text>
        <text x="250" y="48" fontSize="9" fontWeight="700" fill={short ? "var(--v-destructive)" : "var(--v-foreground)"}>{kes(gap)}</text>
      </svg>
      <figcaption className="text-[11px] text-[var(--v-muted-foreground)]">
        {example ? "Example, not a recorded count. " : ""}Window: {windowLabel}. Till {kes(expected)}, counted {kes(counted)}. {trick || reason || "This count is not short."}
      </figcaption>
    </figure>
  );
}
