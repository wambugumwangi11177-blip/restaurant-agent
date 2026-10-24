import { kes } from "@/lib/owner/format";
import ChartEmpty from "./ChartEmpty";

export type CurvePoint = { at: string; sales: number };

type Props = {
  points: CurvePoint[];
  breakEven: number;
  coveredAt: string | null;
  toGo: number;
  label?: string;
};

const W = 320;
const H = 140;
const PAD = { top: 16, right: 8, bottom: 22, left: 8 };

/** Cumulative sales today against the break-even line. The crossing time is marked when sales have passed it. */
export default function BreakEvenLine({ points, breakEven, coveredAt, toGo, label = "Sales today against the costs this day has to cover" }: Props) {
  if (points.length === 0 || breakEven <= 0) {
    return <ChartEmpty state="no_data" reason="Once today's sales are recorded, this line climbs toward the costs the day has to cover." height={H} />;
  }
  const max = Math.max(breakEven, ...points.map((p) => p.sales), 1);
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;
  const x = (i: number) => PAD.left + (points.length === 1 ? plotW / 2 : (i / (points.length - 1)) * plotW);
  const y = (v: number) => PAD.top + plotH - (v / max) * plotH;
  const line = points.map((p, i) => `${i === 0 ? "M" : "L"} ${x(i).toFixed(1)} ${y(p.sales).toFixed(1)}`).join(" ");
  const beY = y(breakEven);
  const cross = coveredAt ? points.findIndex((p) => p.sales >= breakEven) : -1;
  return (
    <figure>
      <svg role="img" aria-label={label} viewBox={`0 0 ${W} ${H}`} className="w-full">
        <line x1={PAD.left} x2={W - PAD.right} y1={beY} y2={beY} stroke="var(--chart-cost, #fbbf24)" strokeDasharray="4 3" />
        <text x={W - PAD.right} y={Math.max(10, beY - 4)} textAnchor="end" fontSize="8" fill="var(--chart-cost, #fbbf24)">Costs {kes(breakEven)}</text>
        <path d={line} fill="none" stroke="var(--chart-bar, #e0b15a)" strokeWidth="2" strokeLinejoin="round" />
        {points.map((p, i) => <circle key={`${p.at}-${i}`} cx={x(i)} cy={y(p.sales)} r={i === cross ? 3.5 : 2} fill={i === cross ? "var(--success, #4ade80)" : "var(--chart-bar, #e0b15a)"}><title>{p.at}: sales {kes(p.sales)}</title></circle>)}
        <text x={PAD.left} y={H - 6} fontSize="8" fill="var(--v-muted-foreground)">{points[0].at}</text>
        <text x={W - PAD.right} y={H - 6} textAnchor="end" fontSize="8" fill="var(--v-muted-foreground)">{points[points.length - 1].at}</text>
      </svg>
      <figcaption className="mt-1 text-xs"><span className="mr-3">Sales so far</span><span>Costs this service has to cover</span>. {coveredAt ? `Sales crossed that line at ${coveredAt}.` : `${kes(toGo)} still to cover.`}</figcaption>
    </figure>
  );
}
