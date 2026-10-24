import { kes } from "@/lib/owner/format";
import ChartEmpty from "./ChartEmpty";

export type ToleranceDot = { key: string; expected: number; gap: number; label: string };

type Props = { toleranceKes: number; tolerancePct: number; dots: ToleranceDot[]; label?: string };

const W = 320;
const H = 140;
const PAD = { l: 28, r: 8, t: 12, b: 22 };

/** The difference the owner accepts, as a curve, with each shift's actual gap as a dot. */
export default function ToleranceCurve({ toleranceKes, tolerancePct, dots, label = "Cash difference you accept" }: Props) {
  if (!(toleranceKes > 0) && !(tolerancePct > 0)) {
    return <ChartEmpty state="no_data" reason="Set the cash difference you accept and this curve shows which counts sit outside it." height={H} />;
  }
  const maxExpected = Math.max(1000, ...dots.map((d) => d.expected), toleranceKes * 4);
  const allowed = (expected: number) => Math.max(toleranceKes, expected * (tolerancePct / 100));
  const maxY = Math.max(allowed(maxExpected), ...dots.map((d) => Math.abs(d.gap)), 1);
  const x = (v: number) => PAD.l + (v / maxExpected) * (W - PAD.l - PAD.r);
  const y = (v: number) => PAD.t + (H - PAD.t - PAD.b) * (1 - v / maxY);
  const curve = Array.from({ length: 17 }, (_, i) => {
    const expected = (maxExpected * i) / 16;
    return `${i === 0 ? "M" : "L"} ${x(expected).toFixed(1)} ${y(allowed(expected)).toFixed(1)}`;
  }).join(" ");
  return (
    <figure>
      <svg role="img" aria-label={label} viewBox={`0 0 ${W} ${H}`} className="w-full">
        <path d={curve} fill="none" stroke="var(--v-warn)" strokeWidth="1.6" />
        <text x={PAD.l} y={12} fontSize="8" fill="var(--v-muted-foreground)">Accept {kes(toleranceKes)} or {tolerancePct}%</text>
        {dots.map((d) => (
          <circle key={d.key} cx={x(d.expected)} cy={y(Math.abs(d.gap))} r="3.2" fill={Math.abs(d.gap) > allowed(d.expected) ? "var(--v-destructive)" : "var(--v-good)"}>
            <title>{d.label}: difference {kes(d.gap)}, accept {kes(allowed(d.expected))}</title>
          </circle>
        ))}
      </svg>
      <figcaption className="text-[11px] text-[var(--v-muted-foreground)]">
        {dots.length === 0 ? "No counts yet. The line is the difference you accept. Each count will appear as a dot." : "A dot above the line is a count outside what you accept."}
      </figcaption>
    </figure>
  );
}
