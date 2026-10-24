import { kes } from "@/lib/owner/format";
import ChartEmpty from "./ChartEmpty";

export type MatchLeg = { key: string; label: string; left: string; right: string; gap: string; look: boolean };

/** Cash counted, M-Pesa on the statement, and card: three legs of one shift. */
export default function ThreeWayMatch({ legs, label = "Three-way match for the latest shift" }: { legs: MatchLeg[]; label?: string }) {
  if (legs.length === 0) return <ChartEmpty state="no_data" reason="A cash count, an M-Pesa statement and card sales will meet here for each shift." height={120} />;
  return (
    <figure>
      <svg role="img" aria-label={label} viewBox="0 0 320 100" className="mx-auto w-full max-w-xs">
        <polygon points="160,12 78,88 242,88" fill="none" stroke="var(--chart-bar, #e0b15a)" strokeWidth="1.5" />
        {legs.slice(0, 3).map((leg, i) => {
          const dot = [{ x: 160, y: 12 }, { x: 78, y: 88 }, { x: 242, y: 88 }][i];
          return <circle key={leg.key} cx={dot.x} cy={dot.y} r="4" fill={leg.look ? "var(--danger, #f87171)" : "var(--chart-bar, #e0b15a)"}><title>{leg.label}</title></circle>;
        })}
      </svg>
      <ul className="mt-2 grid gap-2 sm:grid-cols-3">
        {legs.map((leg) => (
          <li key={leg.key} className="rounded-lg border border-[var(--v-border)] p-2 text-xs">
            <b className="block">{leg.label}</b>
            <span className="text-[var(--v-muted-foreground)]">{leg.left} against {leg.right}. {leg.look ? `Difference ${leg.gap}.` : "Inside what you accept."}</span>
          </li>
        ))}
      </ul>
    </figure>
  );
}

export function leg(key: string, label: string, leftKes: number | null, rightKes: number | null, look: boolean): MatchLeg | null {
  if (leftKes == null || rightKes == null) return null;
  return { key, label, left: kes(leftKes), right: kes(rightKes), gap: kes(Math.abs(leftKes - rightKes)), look };
}
