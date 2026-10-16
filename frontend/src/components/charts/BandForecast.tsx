import { kesShort, shortDay, weekday } from "@/lib/owner/format";
import ChartEmpty, { isEmpty, type ChartStateProps } from "./ChartEmpty";

export type ActualDay = { date: string; sales: number };
export type ForecastDay = { date: string; usual: number; low: number; high: number };
export type UnusualDay = { date: string; sales: number; expected: number };

type Props = ChartStateProps & {
  actual: ActualDay[];
  next: ForecastDay[];
  unusual?: UnusualDay[];
  label: string;
  height?: number;
};

const W = 320;
const PAD = { l: 34, r: 6, t: 8, b: 20 };

/** What sold lately as a line, and what is likely next as a band (low to high) around the usual: a range, never one number. */
export default function BandForecast({ actual, next, unusual = [], label, height = 150, state, reason, day, of }: Props) {
  if (isEmpty(state) || (actual.length < 2 && next.length === 0)) return <ChartEmpty state={state ?? "no_data"} reason={reason} day={day} of={of} height={height} />;
  const days = [...actual.map((a) => a.date), ...next.map((n) => n.date)];
  const top = Math.max(1, ...actual.map((a) => a.sales), ...next.map((n) => n.high), ...unusual.map((u) => u.sales));
  const x = (i: number) => PAD.l + (i / Math.max(days.length - 1, 1)) * (W - PAD.l - PAD.r);
  const y = (v: number) => PAD.t + (1 - v / top) * (height - PAD.t - PAD.b);
  const offset = actual.length;
  const line = actual.map((a, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(a.sales).toFixed(1)}`).join(" ");
  const band = next.length
    ? `${next.map((n, i) => `${i ? "L" : "M"}${x(offset + i).toFixed(1)} ${y(n.high).toFixed(1)}`).join(" ")} ${[...next].reverse().map((n, i) => `L${x(offset + next.length - 1 - i).toFixed(1)} ${y(n.low).toFixed(1)}`).join(" ")} Z`
    : "";
  const usual = next.map((n, i) => `${i ? "L" : "M"}${x(offset + i).toFixed(1)} ${y(n.usual).toFixed(1)}`).join(" ");
  const ticks = [0, Math.floor((days.length - 1) / 2), days.length - 1];
  return (
    <svg role="img" aria-label={label} viewBox={`0 0 ${W} ${height}`} className="mx-auto w-full max-w-[34rem]">
      {[0, 0.5, 1].map((f) => (
        <g key={f}>
          <line x1={PAD.l} x2={W - PAD.r} y1={y(top * f)} y2={y(top * f)} stroke="var(--v-border)" strokeDasharray={f ? "2 3" : undefined} />
          <text x={PAD.l - 4} y={y(top * f) + 3} textAnchor="end" fontSize="8" fill="var(--v-muted-foreground)">{kesShort(top * f).replace("KES ", "")}</text>
        </g>
      ))}
      {next.length > 0 && <line x1={x(offset - 0.5)} x2={x(offset - 0.5)} y1={PAD.t} y2={height - PAD.b} stroke="var(--v-border)" />}
      {band && <path d={band} fill="var(--v-accent)" opacity="0.55"><title>{`Likely range for the next ${next.length} days`}</title></path>}
      {usual && <path d={usual} fill="none" stroke="var(--v-sidebar-primary)" strokeWidth="1.6" strokeDasharray="4 3" />}
      {line && <path d={line} fill="none" stroke="var(--v-primary)" strokeWidth="2" strokeLinejoin="round" />}
      {unusual.map((u) => {
        const i = days.indexOf(u.date);
        return i < 0 ? null : <circle key={u.date} cx={x(i)} cy={y(u.sales)} r="3.2" fill="var(--v-destructive)"><title>{`${shortDay(u.date)}: ${Math.round(u.sales)} against about ${Math.round(u.expected)} expected`}</title></circle>;
      })}
      {ticks.map((i) => (
        <text key={i} x={x(i)} y={height - 5} textAnchor={i === 0 ? "start" : i === days.length - 1 ? "end" : "middle"} fontSize="8.5" fill="var(--v-muted-foreground)">{`${weekday(days[i])} ${shortDay(days[i])}`}</text>
      ))}
    </svg>
  );
}
