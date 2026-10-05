"use client";
// Small dependency-free SVG charts for the Demo Restaurant. Every chart states its
// figures in text as well (aria-label and visible labels), so nothing is colour-only.
import { fmtKes } from "@/lib/format";

export type LineBandChart = {
  type: "line_band";
  title: string;
  actual: { date: string; day: string; revenue: number }[];
  forecast: { date: string; day: string; revenue: number; low: number; high: number }[];
};
export type DonutChart = {
  type: "donut";
  title: string;
  slices: { label: string; value: number }[];
};
export type MeterChart = {
  type: "meters";
  title: string;
  unit: string;
  target?: number;
  items: { label: string; value: number; note?: string; status: "ok" | "watch" | "low" }[];
};
export type DemoChart = LineBandChart | DonutChart | MeterChart;

const PALETTE = [
  "hsl(201 47% 29%)",
  "hsl(43 76% 57%)",
  "hsl(160 30% 45%)",
  "hsl(24 65% 45%)",
  "hsl(260 30% 60%)",
  "hsl(210 10% 60%)",
];

const k = (v: number) => `${Math.round(v / 1000)}k`;

export function ChartFrame({ title, note, children }: { title: string; note?: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-5">
      <h2 className="font-display text-xl">{title}</h2>
      {note && <p className="mt-1 text-xs text-[var(--v-muted-foreground)]">{note}</p>}
      <div className="mt-4">{children}</div>
    </section>
  );
}

export function LineBand({
  chart,
  selected,
  onSelect,
}: {
  chart: LineBandChart;
  selected?: string | null;
  onSelect?: (date: string) => void;
}) {
  const W = 640, H = 270, L = 46, R = 14, T = 14, B = 34;
  const a = chart.actual.length;
  const n = a + chart.forecast.length;
  const max = Math.max(...chart.actual.map((r) => r.revenue), ...chart.forecast.map((r) => r.high)) * 1.08;
  const x = (i: number) => L + (i * (W - L - R)) / (n - 1);
  const y = (v: number) => T + (1 - v / max) * (H - T - B);
  const last = chart.actual[a - 1];
  const actualPath = chart.actual.map((r, i) => `${i ? "L" : "M"}${x(i)},${y(r.revenue)}`).join(" ");
  const forecastPath = [`M${x(a - 1)},${y(last.revenue)}`, ...chart.forecast.map((r, i) => `L${x(a + i)},${y(r.revenue)}`)].join(" ");
  const upper = chart.forecast.map((r, i) => `L${x(a + i)},${y(r.high)}`).join(" ");
  const lower = [...chart.forecast].reverse().map((r, i) => `L${x(n - 1 - i)},${y(r.low)}`).join(" ");
  const band = `M${x(a - 1)},${y(last.revenue)} ${upper} ${lower} Z`;
  const ticks = [0, 1, 2, 3].map((t) => (max / 3) * t);
  const label = `${chart.title}. Recent sales ${chart.actual.map((r) => `${r.day} ${fmtKes(r.revenue)}`).join(", ")}. Expected ${chart.forecast.map((r) => `${r.day} ${fmtKes(r.revenue)}`).join(", ")}.`;
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label={label}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} stroke="hsl(40 20% 86%)" strokeWidth="1" />
            <text x={L - 6} y={y(t) + 3} textAnchor="end" fontSize="10" fill="hsl(207 12% 46%)">{k(t)}</text>
          </g>
        ))}
        <path d={band} fill="hsl(43 76% 57% / 0.22)" />
        <line x1={x(a - 1)} x2={x(a - 1)} y1={T} y2={H - B} stroke="hsl(207 12% 46%)" strokeDasharray="3 4" />
        <text x={x(a - 1)} y={T + 8} textAnchor="middle" fontSize="10" fontWeight="700" fill="hsl(207 12% 46%)">Today</text>
        <path d={actualPath} fill="none" stroke="hsl(201 47% 29%)" strokeWidth="2.5" strokeLinejoin="round" />
        <path d={forecastPath} fill="none" stroke="hsl(35 80% 42%)" strokeWidth="2.5" strokeDasharray="6 5" />
        {chart.actual.map((r, i) => (
          <circle key={r.date} cx={x(i)} cy={y(r.revenue)} r="3" fill="hsl(201 47% 29%)" />
        ))}
        {chart.forecast.map((r, i) => {
          const on = selected === r.date;
          return (
            <g
              key={r.date}
              role="button"
              tabIndex={0}
              aria-label={`${r.day} ${r.date.slice(5)}: expect ${fmtKes(r.revenue)}. Show why.`}
              aria-pressed={on}
              className="cursor-pointer outline-none"
              onClick={() => onSelect?.(r.date)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSelect?.(r.date);
                }
              }}
            >
              <circle cx={x(a + i)} cy={y(r.revenue)} r="16" fill="transparent" />
              <circle cx={x(a + i)} cy={y(r.revenue)} r={on ? 7 : 4.5} fill={on ? "hsl(35 80% 42%)" : "white"} stroke="hsl(35 80% 42%)" strokeWidth="2.5" />
            </g>
          );
        })}
        {[...chart.actual, ...chart.forecast].map((r, i) =>
          i % 2 === 0 || i >= a ? (
            <text key={r.date} x={x(i)} y={H - 12} textAnchor="middle" fontSize="10" fill="hsl(207 12% 46%)" fontWeight={i >= a ? 700 : 400}>
              {r.day}
            </text>
          ) : null,
        )}
      </svg>
      <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-[11px] text-[var(--v-muted-foreground)]">
        <span className="inline-flex items-center gap-2"><span className="h-0.5 w-5 bg-[hsl(201_47%_29%)]" />What happened</span>
        <span className="inline-flex items-center gap-2"><span className="h-0.5 w-5 border-t-2 border-dashed border-[hsl(35_80%_42%)]" />What we expect</span>
        <span className="inline-flex items-center gap-2"><span className="h-3 w-5 rounded-sm bg-[hsl(43_76%_57%_/_0.35)]" />Usual range</span>
      </div>
    </div>
  );
}

export function LineSeries({ series, label }: { series: { date: string; day: string; revenue: number }[]; label: string }) {
  const W = 640, H = 220, L = 46, R = 14, T = 12, B = 30;
  const n = Math.max(series.length, 2);
  const max = Math.max(...series.map((r) => r.revenue), 1) * 1.1;
  const x = (i: number) => L + (i * (W - L - R)) / (n - 1);
  const y = (v: number) => T + (1 - v / max) * (H - T - B);
  const path = series.map((r, i) => `${i ? "L" : "M"}${x(i)},${y(r.revenue)}`).join(" ");
  const area = `${path} L${x(series.length - 1)},${y(0)} L${x(0)},${y(0)} Z`;
  const step = Math.max(1, Math.ceil(series.length / 8));
  const ticks = [0, 1, 2, 3].map((t) => (max / 3) * t);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label={`${label}. ${series.map((r) => `${r.date.slice(5)} ${fmtKes(r.revenue)}`).join(", ")}`}>
      {ticks.map((t) => (
        <g key={t}>
          <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} stroke="hsl(40 20% 86%)" />
          <text x={L - 6} y={y(t) + 3} textAnchor="end" fontSize="10" fill="hsl(207 12% 46%)">{k(t)}</text>
        </g>
      ))}
      <path d={area} fill="hsl(201 47% 29% / 0.10)" />
      <path d={path} fill="none" stroke="hsl(201 47% 29%)" strokeWidth="2.5" strokeLinejoin="round" />
      {series.map((r, i) => (
        <g key={r.date}>
          {series.length <= 31 && <circle cx={x(i)} cy={y(r.revenue)} r="3" fill="hsl(201 47% 29%)" />}
          {i % step === 0 && (
            <text x={x(i)} y={H - 10} textAnchor="middle" fontSize="10" fill="hsl(207 12% 46%)">
              {series.length <= 8 && r.day !== "wk" ? r.day : r.date.slice(5)}
            </text>
          )}
        </g>
      ))}
    </svg>
  );
}

export function WeekdayBars({ pattern }: { pattern: { day: string; revenue: number }[] }) {
  const max = Math.max(...pattern.map((p) => p.revenue), 1);
  const peak = pattern.reduce((best, p) => (p.revenue > best.revenue ? p : best), pattern[0]);
  return (
    <div role="img" aria-label={`Average sales by weekday. ${pattern.map((p) => `${p.day} ${fmtKes(p.revenue)}`).join(", ")}. Busiest: ${peak.day}.`}>
      {/* Each bar is a percentage of a track with a fixed height (a percentage of an auto-height parent collapses). */}
      <div className="flex items-end gap-2 pt-4">
        {pattern.map((p) => {
          const share = Math.max((p.revenue / max) * 100, 4);
          return (
            <div key={p.day} className="flex flex-1 flex-col items-center gap-1.5">
              <div className="relative h-32 w-full">
                <span className="absolute inset-x-0 text-center text-[9px] text-[var(--v-muted-foreground)]" style={{ bottom: `calc(${share}% + 4px)` }}>
                  {k(p.revenue)}
                </span>
                <div
                  className="absolute bottom-0 w-full rounded-t-md"
                  style={{ height: `${share}%`, background: p === peak ? "hsl(43 76% 57%)" : "hsl(201 47% 29% / 0.8)" }}
                />
              </div>
              <span className="text-[10px] font-semibold">{p.day}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function Donut({ slices, unit = "KES" }: { slices: { label: string; value: number }[]; unit?: "KES" | "count" }) {
  const total = slices.reduce((s, x) => s + x.value, 0) || 1;
  let acc = 0;
  const fmt = (v: number) => (unit === "KES" ? fmtKes(v) : `${v}`);
  return (
    <div className="flex flex-col items-center gap-5 sm:flex-row">
      <svg viewBox="0 0 42 42" className="h-40 w-40 shrink-0" role="img" aria-label={slices.map((s) => `${s.label} ${Math.round((s.value / total) * 100)}%`).join(", ")}>
        <circle cx="21" cy="21" r="15.9155" fill="none" stroke="hsl(40 20% 90%)" strokeWidth="5.5" />
        {slices.map((s, i) => {
          const pct = (s.value / total) * 100;
          const seg = (
            <circle
              key={s.label}
              cx="21"
              cy="21"
              r="15.9155"
              fill="none"
              stroke={PALETTE[i % PALETTE.length]}
              strokeWidth="5.5"
              strokeDasharray={`${pct} ${100 - pct}`}
              strokeDashoffset={25 - acc}
            />
          );
          acc += pct;
          return seg;
        })}
        <text x="21" y="22.5" textAnchor="middle" fontSize="5" fontWeight="700" fill="hsl(208 29% 19%)">{unit === "KES" ? k(total) : total}</text>
      </svg>
      <ul className="w-full space-y-2 text-sm">
        {slices.map((s, i) => (
          <li key={s.label} className="flex items-center justify-between gap-3">
            <span className="inline-flex items-center gap-2">
              <span className="h-3 w-3 rounded-sm" style={{ background: PALETTE[i % PALETTE.length] }} />
              {s.label}
            </span>
            <span className="text-[var(--v-muted-foreground)]">
              {fmt(s.value)} · {Math.round((s.value / total) * 100)}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function Meters({ chart }: { chart: MeterChart }) {
  const max = Math.max(...chart.items.map((i) => i.value), chart.target ?? 0, 1);
  const tone = { low: "hsl(0 60% 48%)", watch: "hsl(43 76% 50%)", ok: "hsl(201 47% 29%)" } as const;
  const words = { low: "Order soon", watch: "Use first", ok: "" } as const;
  const show = (v: number) => (chart.unit === "KES" ? fmtKes(v) : `${v} ${chart.unit}`);
  return (
    <ul className="space-y-3">
      {chart.items.map((item) => (
        <li key={item.label}>
          <div className="flex items-baseline justify-between gap-3 text-sm">
            <span className="font-medium">
              {item.label}
              {words[item.status] && (
                <span className="ml-2 rounded-full px-2 py-0.5 text-[10px] font-bold text-white" style={{ background: tone[item.status] }}>
                  {words[item.status]}
                </span>
              )}
            </span>
            <span className="text-xs text-[var(--v-muted-foreground)]">
              {show(item.value)}
              {item.note ? ` · ${item.note}` : ""}
            </span>
          </div>
          <div className="relative mt-1.5 h-2.5 rounded-full bg-[hsl(40_20%_90%)]" role="img" aria-label={`${item.label}: ${show(item.value)}`}>
            <div className="h-full rounded-full" style={{ width: `${Math.max((item.value / max) * 100, 3)}%`, background: tone[item.status] }} />
            {chart.target != null && (
              <span className="absolute -top-1 w-0.5 bg-[hsl(208_29%_19%)]" style={{ left: `${(chart.target / max) * 100}%`, height: "18px" }} title={`Order when cover is ${chart.target} ${chart.unit} or less`} />
            )}
          </div>
        </li>
      ))}
      {chart.target != null && <li className="text-[11px] text-[var(--v-muted-foreground)]">The dark mark is {chart.target} {chart.unit}: order when an ingredient reaches it.</li>}
    </ul>
  );
}

export function RenderChart({
  chart,
  selectedDate,
  onSelectDate,
}: {
  chart: DemoChart;
  selectedDate?: string | null;
  onSelectDate?: (date: string) => void;
}) {
  if (chart.type === "line_band") {
    return (
      <ChartFrame title={chart.title} note="Tap a coloured dot on the dashed line to see why we expect that amount.">
        <LineBand chart={chart} selected={selectedDate} onSelect={onSelectDate} />
      </ChartFrame>
    );
  }
  if (chart.type === "donut") {
    return (
      <ChartFrame title={chart.title}>
        <Donut slices={chart.slices} />
      </ChartFrame>
    );
  }
  return (
    <ChartFrame title={chart.title}>
      <Meters chart={chart} />
    </ChartFrame>
  );
}
