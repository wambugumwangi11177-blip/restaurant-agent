import { kes, kesShort, shortDay } from "@/lib/owner/format";
import ChartEmpty, { isEmpty, type ChartStateProps } from "./ChartEmpty";

export type RunwayDay = { date: string; balance: number; bills: number };

type Props = ChartStateProps & { days: RunwayDay[]; label: string; height?: number };

const W = 320;
const PAD = { l: 38, r: 6, t: 10, b: 20 };

/**
 * The cash you will have, day by day: what you keep from sales after ingredients and wages, less the bills as they fall due.
 * Where the line goes under zero the area is red — that is the day you will be short — and every bill is a dot on its day.
 */
export default function CashRunway({ days, label, height = 150, state, reason, day, of }: Props) {
  if (isEmpty(state) || days.length < 2) return <ChartEmpty state={state ?? "no_data"} reason={reason} day={day} of={of} height={height} />;
  const lo = Math.min(0, ...days.map((d) => d.balance));
  const hi = Math.max(0, ...days.map((d) => d.balance));
  const span = hi - lo || 1;
  const x = (i: number) => PAD.l + (i / (days.length - 1)) * (W - PAD.l - PAD.r);
  const y = (v: number) => PAD.t + (1 - (v - lo) / span) * (height - PAD.t - PAD.b);
  const line = days.map((d, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(d.balance).toFixed(1)}`).join(" ");
  const below = `${line} L${x(days.length - 1)} ${y(0)} L${x(0)} ${y(0)} Z`;
  const shortDays = days.filter((d) => d.balance < 0).length;
  return (
    <figure>
      <svg role="img" aria-label={`${label}${shortDays ? `: short on ${shortDays} of the next ${days.length} days` : ": enough for every bill"}`} viewBox={`0 0 ${W} ${height}`} className="mx-auto w-full max-w-[34rem]">
        <clipPath id="runway-below"><rect x={PAD.l} y={y(0)} width={W - PAD.l - PAD.r} height={Math.max(height - PAD.b - y(0), 0)} /></clipPath>
        <clipPath id="runway-above"><rect x={PAD.l} y={PAD.t} width={W - PAD.l - PAD.r} height={Math.max(y(0) - PAD.t, 0)} /></clipPath>
        <path d={below} fill="var(--v-destructive)" opacity="0.2" clipPath="url(#runway-below)" />
        <path d={below} fill="var(--v-good)" opacity="0.14" clipPath="url(#runway-above)" />
        <line x1={PAD.l} x2={W - PAD.r} y1={y(0)} y2={y(0)} stroke="var(--v-foreground)" strokeOpacity="0.45" />
        <text x={PAD.l - 4} y={y(0) + 3} textAnchor="end" fontSize="8" fill="var(--v-muted-foreground)">0</text>
        <text x={PAD.l - 4} y={y(hi) + 8} textAnchor="end" fontSize="8" fill="var(--v-muted-foreground)">{kesShort(hi).replace("KES ", "")}</text>
        {lo < 0 && <text x={PAD.l - 4} y={y(lo) - 2} textAnchor="end" fontSize="8" fill="var(--v-destructive)">{kesShort(lo).replace("KES ", "")}</text>}
        <path d={line} fill="none" stroke="var(--v-primary)" strokeWidth="2" strokeLinejoin="round" />
        {days.map((d, i) => d.bills > 0 && (
          <circle key={d.date} cx={x(i)} cy={y(d.balance)} r="4" fill="var(--v-sidebar-primary)" stroke="var(--v-foreground)" strokeWidth="1">
            <title>{`${shortDay(d.date)}: bills ${kes(d.bills)}, left ${kes(d.balance)}`}</title>
          </circle>
        ))}
        {[0, days.length - 1].map((i) => (
          <text key={i} x={x(i)} y={height - 5} textAnchor={i === 0 ? "start" : "end"} fontSize="8.5" fill="var(--v-muted-foreground)">{shortDay(days[i].date)}</text>
        ))}
      </svg>
      <figcaption className="mt-1 text-[10px] text-[var(--v-muted-foreground)]">Gold dots are bills falling due. Red is the days you would be short.</figcaption>
    </figure>
  );
}
