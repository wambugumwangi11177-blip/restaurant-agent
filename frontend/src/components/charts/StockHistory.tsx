import type { BlockState } from "@/lib/owner/types";
import ChartEmpty from "./ChartEmpty";

type Point = { date: string; on_hand: number };

/** On-hand over the last days, with the reorder line. */
export default function StockHistory({ item, unit, points, reorder, par, state, reason, windowLabel = "last 14 days" }: {
  item?: string; unit?: string; points?: Point[]; reorder?: number | null; par?: number | null;
  state?: BlockState; reason?: string | null; windowLabel?: string;
}) {
  if (!points || points.length < 2 || state === "no_data" || state === "unavailable") {
    return <ChartEmpty state={state ?? "no_data"} reason={reason || "Stock history draws once an item moves."} height={120} />;
  }
  const values = points.map((p) => p.on_hand);
  const top = Math.max(...values, reorder ?? 0, par ?? 0, 1) * 1.1;
  const y = (v: number) => 100 - (v / top) * 80;
  const x = (i: number) => 28 + (i / Math.max(points.length - 1, 1)) * 270;
  const line = points.map((p, i) => `${x(i)},${y(p.on_hand)}`).join(" ");
  return (
    <figure>
      <svg role="img" aria-label={`${item ?? "Stock"} on hand, ${windowLabel}`} viewBox="0 0 320 120" className="w-full">
        <polyline points={line} fill="none" stroke="var(--v-primary)" strokeWidth="2" />
        {reorder != null && <line x1="24" x2="300" y1={y(reorder)} y2={y(reorder)} stroke="var(--v-warn)" strokeDasharray="4 3" />}
        {par != null && par > 0 && <line x1="24" x2="300" y1={y(par)} y2={y(par)} stroke="var(--v-good)" strokeDasharray="2 3" />}
        <text x="28" y="14" fontSize="9" fill="var(--v-muted-foreground)">{item} · {windowLabel}</text>
      </svg>
      <figcaption className="text-[11px] text-[var(--v-muted-foreground)]">
        {points[points.length - 1].on_hand} {unit} on hand now{reorder != null ? `, reorder at ${reorder} ${unit}` : ""}.
      </figcaption>
    </figure>
  );
}
