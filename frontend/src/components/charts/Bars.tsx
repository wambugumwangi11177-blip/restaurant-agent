import ChartEmpty, { isEmpty, type ChartStateProps } from "./ChartEmpty";

export type Bar = { key: string; label: string; value: number; /** read aloud and shown on hover: "Wed 14 Oct: KES 18,250 · 19 orders" */ title: string; highlight?: boolean };

type Props = ChartStateProps & {
  bars: Bar[];
  /** What the whole chart says, for a screen reader: "Sales, last 7 days". */
  label: string;
  /** Format a bar's value for the label drawn above it; omit to draw none. */
  format?: (value: number) => string;
  height?: number;
};

const W = 320;
const PAD = { top: 22, bottom: 22, side: 4 };

/** Vertical bars with the best one in gold. Bars always start at zero: a shorter bar is a smaller number, never a rescaled one. */
export default function Bars({ bars, label, format, height = 120, state, reason, day, of }: Props) {
  if (isEmpty(state) || bars.length === 0) return <ChartEmpty state={state ?? "no_data"} reason={reason} day={day} of={of} height={height} />;
  const max = Math.max(...bars.map((b) => b.value), 1);
  const slot = (W - PAD.side * 2) / bars.length;
  const barW = Math.min(slot * 0.62, 34);
  const plot = height - PAD.top - PAD.bottom;
  const dense = bars.length > 8;
  return (
    <svg role="img" aria-label={label} viewBox={`0 0 ${W} ${height}`} className="w-full" style={{ maxHeight: height * 1.6 }}>
      <line x1={PAD.side} x2={W - PAD.side} y1={height - PAD.bottom} y2={height - PAD.bottom} stroke="var(--chart-line, #60a5fa)" strokeOpacity="0.35" />
      {bars.map((b, i) => {
        const h = Math.max((b.value / max) * plot, b.value > 0 ? 2 : 0);
        const x = PAD.side + slot * i + (slot - barW) / 2;
        const y = height - PAD.bottom - h;
        const showLabel = !dense || i % 2 === 0;
        return (
          <g key={b.key}>
            <title>{b.title}</title>
            <rect x={x} y={y} width={barW} height={h} rx={3} fill={b.highlight ? "var(--chart-cost, #fbbf24)" : "var(--chart-bar, #e0b15a)"} />
            {format && !dense && <text x={x + barW / 2} y={Math.max(10, y - 4)} textAnchor="middle" fontSize="8" fill="var(--text, #f4f4f5)">{format(b.value)}</text>}
            {showLabel && <text x={x + barW / 2} y={height - 6} textAnchor="middle" fontSize="8" fill="var(--text-muted, #d4d4d8)">{b.label}</text>}
          </g>
        );
      })}
    </svg>
  );
}
