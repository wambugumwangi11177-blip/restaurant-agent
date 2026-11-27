"use client";

import {
  Bar,
  BarChart,
  Cell,
  ComposedChart,
  LabelList,
  Line,
  LineChart,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import ExplainedCard, { type Verdict } from "@/components/eleven/charts/ExplainedCard";
import { fmtDay, fmtK, fmtWeekday, pctChange } from "@/lib/chartFormat";
import { formatKes } from "@/lib/formatKes";

const COLORS = ["#c4b5a8", "#8b7d72", "#6b5e55", "#a89a8f"];
const TICK = { fill: "#a1a1aa", fontSize: 10 };
const GREEN = "#6ee7b7";
const RED = "#f87171";

/** Week-on-week verdict. Red if down more than 15% (Eleven guide, health strip rule). */
function weekVerdict(change: number | null, unit: string): Verdict {
  if (change == null) return { tone: "neutral", text: `Nothing to compare with yet.` };
  if (change >= 5) return { tone: "good", text: `Up ${change}% on ${unit}.` };
  if (change <= -15) return { tone: "bad", text: `Down ${Math.abs(change)}% on ${unit}.` };
  if (change <= -5) return { tone: "watch", text: `Down ${Math.abs(change)}% on ${unit}.` };
  return { tone: "neutral", text: `About level with ${unit}.` };
}

export function SalesLineBlock({ data }: { data: { points?: { day: string; revenue_kes: number }[]; has_sales?: boolean; empty?: string } | null }) {
  const pts = data?.points ?? [];
  const has = !!data?.has_sales && pts.length > 0;
  const total = pts.reduce((a, p) => a + p.revenue_kes, 0);
  const avg = pts.length ? total / pts.length : 0;
  const last7 = pts.slice(-7).reduce((a, p) => a + p.revenue_kes, 0);
  const prev7 = pts.slice(-14, -7).reduce((a, p) => a + p.revenue_kes, 0);
  const best = pts.reduce((m, p) => (p.revenue_kes > (m?.revenue_kes ?? -1) ? p : m), pts[0]);
  const worst = pts.reduce((m, p) => (p.revenue_kes < (m?.revenue_kes ?? Infinity) ? p : m), pts[0]);
  const ticks = pts.length > 1 ? [pts[0].day, pts[Math.floor(pts.length / 2)].day, pts[pts.length - 1].day] : undefined;
  return (
    <ExplainedCard
      title="Sales · last 30 days"
      headline={`${formatKes(total)} in ${pts.length} days`}
      sub={`About ${formatKes(avg)} a day`}
      verdict={weekVerdict(pctChange(last7, prev7), "the week before")}
      what={`Each point is one day of paid tickets. Best day ${fmtDay(best?.day)} (${formatKes(best?.revenue_kes)}), slowest ${fmtDay(worst?.day)} (${formatKes(worst?.revenue_kes)}).`}
      why="Verdict compares the last 7 days with the 7 days before. Red if sales are down more than 15%."
      freshness="Live · from your till"
      detailHref={has ? "/eleven/money/sales" : undefined}
      hasData={has}
      emptyHint={data?.empty ?? "Starts when the till connects."}
    >
      <ResponsiveContainer width="100%" height={180}>
        <LineChart data={pts} margin={{ top: 16, right: 12, left: 0, bottom: 0 }}>
          <XAxis dataKey="day" ticks={ticks} tickFormatter={fmtDay} tick={TICK} axisLine={false} tickLine={false} />
          <YAxis width={36} tickFormatter={fmtK} tick={TICK} axisLine={false} tickLine={false} tickCount={4} />
          <Tooltip labelFormatter={(l) => fmtDay(String(l))} formatter={(v) => formatKes(Number(v))} />
          <Line type="monotone" dataKey="revenue_kes" stroke="#c4b5a8" strokeWidth={2} dot={false} />
          {best ? <ReferenceDot x={best.day} y={best.revenue_kes} r={4} fill={GREEN} stroke="none" label={{ value: `Best ${fmtK(best.revenue_kes)}`, position: "top", fill: GREEN, fontSize: 10 }} /> : null}
          {worst ? <ReferenceDot x={worst.day} y={worst.revenue_kes} r={4} fill={RED} stroke="none" label={{ value: `Low ${fmtK(worst.revenue_kes)}`, position: "bottom", fill: RED, fontSize: 10 }} /> : null}
        </LineChart>
      </ResponsiveContainer>
    </ExplainedCard>
  );
}

export function WeekBarsBlock({ data }: { data: { has_sales?: boolean; this_week_kes?: number; last_week_kes?: number; empty?: string } | null }) {
  const has = !!data?.has_sales;
  const thisW = data?.this_week_kes ?? 0;
  const lastW = data?.last_week_kes ?? 0;
  const change = pctChange(thisW, lastW);
  const diff = thisW - lastW;
  return (
    <ExplainedCard
      title="This week vs last"
      headline={`${formatKes(thisW)} this week`}
      sub={change == null ? undefined : `${diff >= 0 ? "+" : "-"}${formatKes(Math.abs(diff))} (${change > 0 ? "+" : ""}${change}%) vs ${formatKes(lastW)} last week`}
      verdict={weekVerdict(change, "last week")}
      what="The last seven days against the seven days before them. The number on each bar is that week's sales in KES."
      why="Same rule as the 30-day line: red if down more than 15%, amber if down 5–15%."
      freshness="Live · from your till"
      hasData={has}
      emptyHint={data?.empty ?? "Starts when the till connects."}
    >
      <ResponsiveContainer width="100%" height={150}>
        <BarChart data={[{ name: "Last week", kes: lastW }, { name: "This week", kes: thisW }]} margin={{ top: 20, right: 8, left: 8, bottom: 0 }}>
          <XAxis dataKey="name" tick={{ fill: "#a1a1aa", fontSize: 11 }} axisLine={false} tickLine={false} />
          <YAxis hide domain={[0, "dataMax"]} />
          <Bar dataKey="kes" radius={[6, 6, 0, 0]}>
            <Cell fill="#6b5e55" />
            <Cell fill="#c4b5a8" />
            <LabelList dataKey="kes" position="top" formatter={(v: unknown) => fmtK(Number(v))} fill="#e4e4e7" fontSize={12} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ExplainedCard>
  );
}

export function ForecastBlock({ data }: { data: { points?: { day: string; low_kes: number; high_kes: number; mid_kes: number }[]; has_sales?: boolean; empty?: string } | null }) {
  const pts = data?.points ?? [];
  const has = !!data?.has_sales && pts.length > 0;
  const rows = pts.map((p) => ({ ...p, base: p.low_kes, band: Math.max(p.high_kes - p.low_kes, 0) }));
  const sumLow = pts.reduce((a, p) => a + p.low_kes, 0);
  const sumHigh = pts.reduce((a, p) => a + p.high_kes, 0);
  const sumMid = pts.reduce((a, p) => a + p.mid_kes, 0);
  return (
    <ExplainedCard
      title="Next 7 days"
      headline={`About ${formatKes(sumMid)}`}
      sub={`Likely between ${formatKes(sumLow)} and ${formatKes(sumHigh)}`}
      verdict={{ tone: "neutral", text: "A range, not a promise." }}
      what="The shaded band is where each day's sales usually land. The line is the middle guess."
      why="Based on your recent sales on the same weekdays. The band widens when your days vary a lot."
      freshness="Assumption · your recent weekday pattern"
      hasData={has}
      emptyHint={data?.empty ?? "Need about a week of sales first."}
    >
      <ResponsiveContainer width="100%" height={170}>
        <ComposedChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <XAxis dataKey="day" tickFormatter={fmtWeekday} tick={TICK} axisLine={false} tickLine={false} />
          <YAxis width={36} tickFormatter={fmtK} tick={TICK} axisLine={false} tickLine={false} tickCount={4} domain={[0, "auto"]} />
          <Tooltip labelFormatter={(l) => fmtDay(String(l))} formatter={(v, n) => (n === "base" ? [formatKes(Number(v)), "Low"] : n === "band" ? [formatKes(Number(v)), "Range width"] : [formatKes(Number(v)), "Middle guess"])} />
          <Bar dataKey="base" stackId="r" fill="transparent" />
          <Bar dataKey="band" stackId="r" fill="#8b7d72" fillOpacity={0.55} radius={[4, 4, 0, 0]} />
          <Line type="monotone" dataKey="mid_kes" stroke="#c4b5a8" strokeWidth={2} dot={{ r: 3 }} />
        </ComposedChart>
      </ResponsiveContainer>
    </ExplainedCard>
  );
}

type Step = { label: string; kes: number };

/** Plain words for P&L lines (Eleven guide, glossary). */
export function plainLine(label: string): string {
  const l = label.toLowerCase();
  if (l === "sales") return "Sales";
  if (l.startsWith("food")) return "Ingredients";
  if (l.startsWith("gross")) return "Left after ingredients";
  if (l.startsWith("bills")) return "Running costs";
  if (l.startsWith("pay")) return "Wages";
  if (l === "net") return "What you kept";
  return label;
}

export function WaterfallBlock({ data, hrefDetail = true }: { data: { steps?: Step[]; has_sales?: boolean; empty?: string } | null; hrefDetail?: boolean }) {
  const steps = data?.steps ?? [];
  const has = !!data?.has_sales && steps.length > 0;
  const sales = steps[0]?.kes ?? 0;
  const net = steps[steps.length - 1]?.kes ?? 0;
  const rows: { name: string; base: number; size: number; text: string; color: string }[] = [];
  let running = 0;
  steps.forEach((s, i) => {
    const subtotal = i === 0 || /gross|net/i.test(s.label);
    if (subtotal) {
      running = s.kes;
      rows.push({ name: plainLine(s.label), base: 0, size: Math.max(s.kes, 0), text: fmtK(s.kes), color: GREEN });
    } else {
      const drop = Math.abs(s.kes);
      running -= drop;
      rows.push({ name: plainLine(s.label), base: Math.max(running, 0), size: drop, text: `-${fmtK(drop)}`, color: RED });
    }
  });
  const keptPct = sales ? Math.round((net / sales) * 1000) / 10 : 0;
  const verdict: Verdict = keptPct >= 15 ? { tone: "good", text: "A healthy share is left at the end." } : keptPct >= 5 ? { tone: "watch", text: "Thin: most of every sale is already spoken for." } : { tone: "bad", text: "Almost nothing is left after costs." };
  return (
    <ExplainedCard
      title="Where the money goes · this month"
      headline={`You kept ${formatKes(net)}`}
      sub={`Out of ${formatKes(sales)} sold: KES ${keptPct} of every KES 100`}
      verdict={verdict}
      what="Read it left to right. Green is money you have; each red step takes some away until what you kept is left."
      why="Sales minus ingredients, running costs and wages. Costs are only as complete as what your team has entered, so a missing cost makes the profit look bigger than it is."
      freshness="As entered · includes costs entered so far"
      detailHref={has && hrefDetail ? "/eleven/money/pnl" : undefined}
      hasData={has}
      emptyHint={data?.empty ?? "Starts when the till connects."}
    >
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={rows} margin={{ top: 20, right: 8, left: 0, bottom: 0 }}>
          <XAxis dataKey="name" tick={{ fill: "#a1a1aa", fontSize: 9 }} interval={0} axisLine={false} tickLine={false} />
          <YAxis hide domain={[0, "dataMax"]} />
          <Bar dataKey="base" stackId="w" fill="transparent" />
          <Bar dataKey="size" stackId="w" radius={[4, 4, 0, 0]}>
            {rows.map((r, i) => (
              <Cell key={i} fill={r.color} />
            ))}
            <LabelList dataKey="text" position="top" fill="#e4e4e7" fontSize={10} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ExplainedCard>
  );
}

export function ShareStackedBlock({
  title,
  caption,
  slices,
  has,
  empty,
  href,
  headline,
  what,
  why,
  freshness,
  verdict,
}: {
  title: string;
  caption: string;
  slices: { name: string; kes: number }[];
  has: boolean;
  empty: string;
  href?: string;
  headline?: string;
  what?: string;
  why?: string;
  freshness?: string;
  verdict?: Verdict;
}) {
  const cleaned = slices.filter((x) => x.kes > 0);
  const total = cleaned.reduce((a, x) => a + x.kes, 0);
  const top = [...cleaned].sort((a, b) => b.kes - a.kes)[0];
  const row: Record<string, number | string> = { id: "mix" };
  cleaned.forEach((x, i) => {
    row[`s${i}`] = x.kes;
  });
  const data = total ? [row] : [];
  return (
    <ExplainedCard
      title={title}
      headline={headline ?? (top && total ? `${plainLine(top.name)} takes the largest share (${Math.round((top.kes / total) * 100)}%)` : undefined)}
      sub={total ? `${formatKes(total)} in total` : undefined}
      verdict={verdict}
      what={what ?? caption}
      why={why}
      freshness={freshness}
      detailHref={href}
      hasData={has && total > 0}
      emptyHint={empty}
    >
      <div className="space-y-3">
        <ResponsiveContainer width="100%" height={36}>
          <BarChart layout="vertical" data={data} stackOffset="expand" margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
            <XAxis type="number" hide domain={[0, 1]} />
            <YAxis type="category" dataKey="id" hide width={0} />
            <Tooltip
              formatter={(v, _n, item) => {
                const i = Number(String(item?.dataKey ?? "").replace("s", ""));
                const label = cleaned[i]?.name ?? "";
                return [formatKes(Number(v)), plainLine(label)];
              }}
            />
            {cleaned.map((x, i) => (
              <Bar key={x.name} dataKey={`s${i}`} stackId="share" fill={COLORS[i % COLORS.length]} radius={i === 0 ? [4, 0, 0, 4] : i === cleaned.length - 1 ? [0, 4, 4, 0] : [0, 0, 0, 0]} />
            ))}
          </BarChart>
        </ResponsiveContainer>
        <ul className="min-w-0 space-y-1.5 text-sm">
          {cleaned.map((x, i) => (
            <li key={x.name} className="flex items-center justify-between gap-2">
              <span className="flex min-w-0 items-center gap-2 text-zinc-300">
                <span className="inline-block h-2.5 w-2.5 shrink-0 rounded-sm" style={{ background: COLORS[i % COLORS.length] }} aria-hidden />
                <span className="truncate">{plainLine(x.name)}</span>
              </span>
              <span className="shrink-0 text-zinc-100">
                {fmtK(x.kes)} <span className="text-zinc-500">· {total ? Math.round((x.kes / total) * 100) : 0}%</span>
              </span>
            </li>
          ))}
        </ul>
      </div>
    </ExplainedCard>
  );
}

type DayPoint = { day: string; revenue_kes: number };

function pairWeekdays(points: DayPoint[]) {
  const sorted = [...points].sort((a, b) => a.day.localeCompare(b.day));
  const last14 = sorted.slice(-14);
  const prevWeek = last14.length > 7 ? last14.slice(0, last14.length - 7) : [];
  const thisWeek = last14.slice(-7);
  return thisWeek.map((p) => {
    const wd = new Date(`${p.day}T12:00:00`).getDay();
    const prev = prevWeek.find((q) => new Date(`${q.day}T12:00:00`).getDay() === wd);
    return { day: fmtWeekday(p.day), this_kes: p.revenue_kes, last_kes: prev?.revenue_kes ?? 0 };
  });
}

export function WeekPairedDetailBlock({
  data,
}: {
  data: { points?: DayPoint[]; has_sales?: boolean; empty?: string } | null;
}) {
  const pts = data?.points ?? [];
  const paired = pairWeekdays(pts);
  const has = !!data?.has_sales && paired.length > 0;
  const thisSum = paired.reduce((a, p) => a + p.this_kes, 0);
  const lastSum = paired.reduce((a, p) => a + p.last_kes, 0);
  const best = paired.reduce((m, p) => (p.this_kes > (m?.this_kes ?? -1) ? p : m), paired[0]);
  const worst = paired.reduce((m, p) => (p.this_kes < (m?.this_kes ?? Infinity) ? p : m), paired[0]);
  const change = pctChange(thisSum, lastSum);
  return (
    <ExplainedCard
      title="Day by day · this week vs last"
      headline={best ? `Strongest ${best.day}: ${formatKes(best.this_kes)}` : undefined}
      sub={change != null ? `${change > 0 ? "+" : ""}${change}% across these seven days` : undefined}
      verdict={weekVerdict(change, "the same days last week")}
      what={`Each pair is the same weekday: this week against last. Weakest day ${worst?.day ?? "—"} (${formatKes(worst?.this_kes ?? 0)}).`}
      why="Shows which day moved the week verdict, not only the two weekly totals."
      freshness="Live · from your till"
      hasData={has}
      emptyHint={data?.empty ?? "Starts when the till connects."}
    >
      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={paired} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <XAxis dataKey="day" tick={TICK} axisLine={false} tickLine={false} />
          <YAxis width={36} tickFormatter={fmtK} tick={TICK} axisLine={false} tickLine={false} tickCount={4} />
          <Tooltip formatter={(v) => formatKes(Number(v))} />
          <Bar dataKey="last_kes" name="Last week" fill="#6b5e55" radius={[4, 4, 0, 0]} />
          <Bar dataKey="this_kes" name="This week" fill="#c4b5a8" radius={[4, 4, 0, 0]}>
            <LabelList dataKey="this_kes" position="top" formatter={(v: unknown) => fmtK(Number(v))} fill="#e4e4e7" fontSize={9} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ExplainedCard>
  );
}
