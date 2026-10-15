import type { BlockState } from "@/lib/owner/types";

/**
 * What a chart says instead of a drawing when it has nothing honest to draw (docs/v2/SPEC.md §3.3: "each takes data + a state and
 * renders an honest empty/learning state itself"). The words come from the block's own reason when it has one.
 */
export type ChartStateProps = {
  state?: BlockState;
  reason?: string | null;
  /** "day 9 of 30" for a learning block. */
  day?: number;
  of?: number;
};

const DEFAULT_REASON: Partial<Record<BlockState, string>> = {
  no_data: "Nothing recorded yet.",
  unavailable: "Not available yet.",
  learning: "Still learning from your history.",
};

/** True when the state means "no chart": the caller returns <ChartEmpty/> and draws nothing. */
export function isEmpty(state?: BlockState): boolean {
  return state === "no_data" || state === "unavailable" || state === "learning";
}

export default function ChartEmpty({ state, reason, day, of, height = 96 }: ChartStateProps & { height?: number }) {
  const learning = state === "learning" && day != null && of != null;
  return (
    <div role="status" style={{ minHeight: height }}
      className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-[var(--v-border)] px-4 py-5 text-center">
      {learning && (
        <div aria-hidden className="h-1.5 w-28 overflow-hidden rounded-full bg-[var(--v-muted)]">
          <div className="h-full rounded-full bg-[var(--v-primary)]" style={{ width: `${Math.min(100, Math.round((day / of) * 100))}%` }} />
        </div>
      )}
      <p className="max-w-sm text-xs leading-relaxed text-[var(--v-muted-foreground)]">
        {learning ? `Learning · day ${day} of ${of}. ` : ""}{reason || (state ? DEFAULT_REASON[state] : "") || ""}
      </p>
    </div>
  );
}
