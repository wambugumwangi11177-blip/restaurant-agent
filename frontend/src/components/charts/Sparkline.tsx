type Props = { values: number[]; label: string; width?: number; height?: number };

/** A line with no axes: the shape of the last few days, for a small space. Fewer than two points draws nothing rather than a dot. */
export default function Sparkline({ values, label, width = 96, height = 28 }: Props) {
  if (values.length < 2) return null;
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const span = hi - lo || 1;
  const pts = values.map((v, i) => `${((i / (values.length - 1)) * (width - 4) + 2).toFixed(1)},${(height - 3 - ((v - lo) / span) * (height - 6)).toFixed(1)}`);
  return (
    <svg role="img" aria-label={label} viewBox={`0 0 ${width} ${height}`} width={width} height={height}>
      <polyline points={pts.join(" ")} fill="none" stroke="var(--v-primary)" strokeWidth="1.8" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={pts[pts.length - 1].split(",")[0]} cy={pts[pts.length - 1].split(",")[1]} r="2.4" fill="var(--v-sidebar-primary)" />
    </svg>
  );
}
