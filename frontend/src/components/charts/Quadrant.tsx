import ChartEmpty, { isEmpty, type ChartStateProps } from "./ChartEmpty";

export type Dish = { name: string; sold: number; /** KES a plate earns: price minus ingredients */ earns: number; kind: string };

type Props = ChartStateProps & {
  dishes: Dish[];
  /** Where "popular" starts (orders) and where "earns well" starts (KES a plate): the engine's own two lines. */
  popularLine?: number | null;
  earnsLine?: number | null;
  label: string;
  height?: number;
};

const W = 320;
const PAD = { l: 30, r: 8, t: 10, b: 24 };
const COLOR: Record<string, string> = {
  "Best dish": "var(--v-good)",
  "Popular, earns little": "var(--v-warn)",
  "Earns well, few order it": "var(--v-primary)",
  "Consider removing": "var(--v-destructive)",
};
const CORNERS: { kind: string; right: boolean; top: boolean }[] = [
  { kind: "Earns well, few order it", right: false, top: true },
  { kind: "Best dish", right: true, top: true },
  { kind: "Consider removing", right: false, top: false },
  { kind: "Popular, earns little", right: true, top: false },
];

/** Every dish as a dot: further right sells more, higher earns more on each plate. The corner it sits in is its word. */
export default function Quadrant({ dishes, popularLine, earnsLine, label, height = 240, state, reason, day, of }: Props) {
  if (isEmpty(state) || dishes.length === 0) return <ChartEmpty state={state ?? "no_data"} reason={reason} day={day} of={of} height={height} />;
  const maxX = Math.max(...dishes.map((d) => d.sold), popularLine ?? 0, 1) * 1.08;
  const maxY = Math.max(...dishes.map((d) => d.earns), earnsLine ?? 0, 1) * 1.08;
  const minY = Math.min(0, ...dishes.map((d) => d.earns));
  const x = (v: number) => PAD.l + (v / maxX) * (W - PAD.l - PAD.r);
  const y = (v: number) => PAD.t + (1 - (v - minY) / (maxY - minY || 1)) * (height - PAD.t - PAD.b);
  return (
    <svg role="img" aria-label={label} viewBox={`0 0 ${W} ${height}`} className="mx-auto w-full max-w-[34rem]">
      <rect x={PAD.l} y={PAD.t} width={W - PAD.l - PAD.r} height={height - PAD.t - PAD.b} fill="none" stroke="var(--v-border)" />
      {popularLine != null && <line x1={x(popularLine)} x2={x(popularLine)} y1={PAD.t} y2={height - PAD.b} stroke="var(--v-border)" strokeDasharray="3 3" />}
      {earnsLine != null && <line x1={PAD.l} x2={W - PAD.r} y1={y(earnsLine)} y2={y(earnsLine)} stroke="var(--v-border)" strokeDasharray="3 3" />}
      {CORNERS.map((c) => (
        <text key={c.kind} x={c.right ? W - PAD.r - 4 : PAD.l + 4} y={c.top ? PAD.t + 11 : height - PAD.b - 5} textAnchor={c.right ? "end" : "start"} fontSize="8" fontWeight="700" fill={COLOR[c.kind]} opacity="0.85">{c.kind}</text>
      ))}
      {dishes.map((d) => (
        <circle key={d.name} cx={x(d.sold)} cy={y(d.earns)} r="4.5" fill={COLOR[d.kind] ?? "var(--v-muted-foreground)"} fillOpacity="0.8" stroke="var(--v-card)" strokeWidth="1">
          <title>{`${d.name}: ${d.sold} sold, earns KES ${Math.round(d.earns)} a plate · ${d.kind}`}</title>
        </circle>
      ))}
      <text x={(PAD.l + W - PAD.r) / 2} y={height - 6} textAnchor="middle" fontSize="8.5" fill="var(--v-muted-foreground)">Sold more →</text>
      <text transform={`translate(9 ${(PAD.t + height - PAD.b) / 2}) rotate(-90)`} textAnchor="middle" fontSize="8.5" fill="var(--v-muted-foreground)">Earns more a plate →</text>
    </svg>
  );
}
