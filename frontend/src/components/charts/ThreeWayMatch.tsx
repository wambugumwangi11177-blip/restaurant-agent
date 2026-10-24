import { kes } from "@/lib/owner/format";
import ChartEmpty from "./ChartEmpty";

export type MatchLeg = { key: string; label: string; left: string; right: string; gap: string; look: boolean };

/** Cash counted, M-Pesa on the statement, and card: three legs of one shift. */
export default function ThreeWayMatch({ legs, label = "Three-way match for the latest shift" }: { legs: MatchLeg[]; label?: string }) {
  if (legs.length === 0) return <ChartEmpty state="no_data" reason="A cash count, an M-Pesa statement and card sales will meet here for each shift." height={120} />;
  return (
    <figure>
      <svg role="img" aria-label={label} viewBox="0 0 320 150" className="w-full">
        <polygon points="160,18 40,128 280,128" fill="none" stroke="var(--v-border)" strokeWidth="1.5" />
        {legs.slice(0, 3).map((leg, i) => {
          const pos = [{ x: 160, y: 28, anchor: "middle" }, { x: 48, y: 118, anchor: "start" }, { x: 272, y: 118, anchor: "end" }][i];
          return (
            <g key={leg.key}>
              <text x={pos.x} y={pos.y} textAnchor={pos.anchor as "middle"} fontSize="9" fontWeight="700" fill={leg.look ? "var(--v-destructive)" : "var(--v-foreground)"}>{leg.label}</text>
              <text x={pos.x} y={pos.y + 12} textAnchor={pos.anchor as "middle"} fontSize="8" fill="var(--v-muted-foreground)">{leg.left} vs {leg.right}</text>
            </g>
          );
        })}
      </svg>
      <ul className="space-y-1 text-[11px]">
        {legs.map((leg) => <li key={leg.key}><b>{leg.label}</b>: {leg.left} against {leg.right}. {leg.look ? `Difference ${leg.gap} — look at this.` : "Inside what you accept."}</li>)}
      </ul>
    </figure>
  );
}

export function leg(key: string, label: string, leftKes: number | null, rightKes: number | null, look: boolean): MatchLeg | null {
  if (leftKes == null || rightKes == null) return null;
  return { key, label, left: kes(leftKes), right: kes(rightKes), gap: kes(Math.abs(leftKes - rightKes)), look };
}
