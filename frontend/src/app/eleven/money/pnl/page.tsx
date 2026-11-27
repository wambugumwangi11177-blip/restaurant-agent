"use client";

import { useEffect, useState } from "react";
import OwnerShell from "@/components/eleven/OwnerShell";
import ExplainedCard, { type Verdict } from "@/components/eleven/charts/ExplainedCard";
import { WaterfallBlock, plainLine } from "@/components/eleven/v11/ChartBlocks";
import api from "@/lib/api";
import { formatKes } from "@/lib/formatKes";

type Line = { line: string; kes: number; pct_sales?: number };

const SLICE_COLORS: Record<string, string> = {
  "Ingredients": "#f87171",
  "Running costs": "#fb923c",
  "Wages": "#a78bfa",
  "What you kept": "#6ee7b7",
};

/** Common ranges for restaurants (Eleven guide, Fig 2.4). Eleven's own targets come from Settings. */
const FOOD_BAND = { lo: 28, hi: 35, max: 60 };
const PRIME_BAND = { lo: 0, hi: 60, max: 90 };

function Dial({ label, plain, value, band, max, verdict }: { label: string; plain: string; value: number; band: { lo: number; hi: number }; max: number; verdict: Verdict }) {
  const pos = (n: number) => `${Math.min(Math.max((n / max) * 100, 0), 100)}%`;
  const word = verdict.tone === "good" ? "In range" : verdict.tone === "watch" ? "Watch" : "Check";
  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between">
        <p className="text-sm text-zinc-100">{label}</p>
        <p className="text-sm text-zinc-100">
          {value}% <span className="text-xs text-zinc-400">· {word}</span>
        </p>
      </div>
      <div className="relative h-3 rounded-full bg-zinc-700/60">
        <div className="absolute inset-y-0 rounded-full bg-emerald-500/40" style={{ left: pos(band.lo), width: `calc(${pos(band.hi)} - ${pos(band.lo)})` }} />
        <div className="absolute top-1/2 h-5 w-1.5 -translate-y-1/2 rounded bg-amber-400" style={{ left: pos(value) }} aria-hidden />
      </div>
      <p className="text-xs text-zinc-400">{plain} Common range {band.lo > 0 ? `${band.lo}–${band.hi}%` : `under ${band.hi}%`}.</p>
    </div>
  );
}

export default function MonthlyPnlPage() {
  const period = new Date().toISOString().slice(0, 7);
  const [data, setData] = useState<{ lines?: Line[]; summary?: string; locked?: boolean } | null>(null);

  useEffect(() => {
    api.get(`/api/v1/eleven/money/pnl/monthly/${period}`).then((r) => setData(r.data));
  }, [period]);

  async function lock() {
    await api.post(`/api/v1/eleven/money/pnl/monthly/${period}/lock`);
    const r = await api.get(`/api/v1/eleven/money/pnl/monthly/${period}`);
    setData(r.data);
  }

  const lines = data?.lines ?? [];
  const find = (re: RegExp) => lines.find((l) => re.test(l.line.toLowerCase()));
  const sales = find(/^sales/);
  const food = find(/^food/);
  const bills = find(/^bills/);
  const pay = find(/^pay/);
  const net = find(/^net/);
  const has = !!sales && sales.kes > 0;
  const pct = (l?: Line) => (l?.pct_sales != null ? l.pct_sales : sales && l ? Math.round((Math.abs(l.kes) / sales.kes) * 1000) / 10 : 0);

  const foodPct = pct(food);
  const primePct = Math.round((foodPct + pct(pay)) * 10) / 10;
  const keptPct = pct(net);
  const slices = has
    ? [
        { name: "Ingredients", pct: foodPct },
        { name: "Running costs", pct: pct(bills) },
        { name: "Wages", pct: pct(pay) },
        { name: "What you kept", pct: keptPct },
      ]
    : [];

  const foodVerdict: Verdict = foodPct <= FOOD_BAND.hi ? { tone: "good", text: "" } : foodPct <= FOOD_BAND.hi + 5 ? { tone: "watch", text: "" } : { tone: "bad", text: "" };
  const primeVerdict: Verdict = primePct <= PRIME_BAND.hi ? { tone: "good", text: "" } : primePct <= 65 ? { tone: "watch", text: "" } : { tone: "bad", text: "" };
  const billsPct = pct(bills);
  const biggest = [...slices].filter((s) => s.name !== "What you kept").sort((a, b) => b.pct - a.pct)[0];
  const keptVerdict: Verdict = keptPct >= 15 ? { tone: "good", text: "A healthy share is left." } : keptPct >= 5 ? { tone: "watch", text: biggest ? `${biggest.name} take the biggest bite (${biggest.pct}%). Check there first.` : "Thin margin." } : { tone: "bad", text: "Almost nothing is left after costs." };

  const steps = lines.map((l) => ({ label: l.line, kes: l.kes }));

  return (
    <OwnerShell title="Full P&L">
      <div className="space-y-3">
        <ExplainedCard
          title="This month so far"
          headline={has ? `You kept ${formatKes(net?.kes)} of ${formatKes(sales?.kes)}` : undefined}
          sub={has ? `KES ${keptPct} of every KES 100 you sold` : undefined}
          verdict={has ? keptVerdict : undefined}
          what="Your profit and loss in plain words: what came in, what each cost took, and what you kept. Your accountant reads the same numbers under their own names."
          why="Costs are only as complete as what your team has entered. If bills or wages are missing, what you kept looks bigger than it really is."
          freshness="As entered · includes costs entered so far"
          hasData={has}
          emptyHint="Starts when the till connects."
        >
          <div className="space-y-3">
            <div className="flex h-5 w-full overflow-hidden rounded-full" role="img" aria-label="Out of every KES 100 of sales">
              {slices.map((s) => (
                <div key={s.name} style={{ width: `${Math.max(s.pct, 0)}%`, background: SLICE_COLORS[s.name] }} title={`${s.name} ${s.pct}%`} />
              ))}
            </div>
            <ul className="space-y-1.5 text-sm">
              {slices.map((s) => (
                <li key={s.name} className="flex items-center justify-between">
                  <span className="flex items-center gap-2 text-zinc-300">
                    <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: SLICE_COLORS[s.name] }} />
                    {s.name}
                  </span>
                  <span className="text-zinc-100">KES {s.pct} <span className="text-zinc-500">of every 100</span></span>
                </li>
              ))}
            </ul>
          </div>
        </ExplainedCard>

        <WaterfallBlock data={has ? { has_sales: true, steps } : null} hrefDetail={false} />

        <ExplainedCard
          title="The two numbers worth watching"
          what="Green is the common healthy range for restaurants; the amber marker is you. A marker that drifts right week after week is the earliest sign ingredients or wages are eating the profit."
          why="Ingredients % = ingredient cost ÷ sales × 100. Ingredients + wages % = (ingredient cost + wages) ÷ sales × 100. Common ranges only: your own targets are set in Settings."
          hasData={has}
          emptyHint="Starts when the till connects."
        >
          <div className="space-y-4">
            <Dial label="Ingredients" plain={`Out of every KES 100 you sold, KES ${foodPct} went on ingredients.`} value={foodPct} band={FOOD_BAND} max={FOOD_BAND.max} verdict={foodVerdict} />
            <Dial label="Ingredients + wages" plain={`Out of every KES 100, KES ${primePct} went on ingredients and wages together.`} value={primePct} band={PRIME_BAND} max={PRIME_BAND.max} verdict={primeVerdict} />
          </div>
        </ExplainedCard>

        <ExplainedCard
          title="Every line"
          what="The same figures as a table, with the proper accounting name under each plain one."
          hasData={has}
          emptyHint="Starts when the till connects."
        >
          <ul className="divide-y divide-zinc-700/50 text-sm">
            {lines.map((row) => (
              <li key={row.line} className="flex items-baseline justify-between py-2">
                <span className="text-zinc-100">
                  {plainLine(row.line)}
                  <span className="block text-[11px] text-zinc-500">{row.line}</span>
                </span>
                <span className="text-right text-zinc-100">
                  {formatKes(row.kes)}
                  {row.pct_sales != null ? <span className="block text-[11px] text-zinc-400">{row.pct_sales}% of sales</span> : null}
                </span>
              </li>
            ))}
          </ul>
        </ExplainedCard>

        {billsPct > 40 ? (
          <p className="owner-glass-panel px-4 py-3 text-sm text-amber-200">
            Running costs are {billsPct}% of sales. Check whether this month includes one-off bills before reading it as normal.
          </p>
        ) : null}

        <div className="flex flex-wrap gap-2">
          <a className="owner-oat-highlight px-3 py-2 text-sm" href={`/api/v1/eleven/money/export/monthly/${period}.xlsx`}>
            Download Excel
          </a>
          <a className="owner-oat-highlight px-3 py-2 text-sm" href={`/api/v1/eleven/money/export/monthly/${period}.pdf`}>
            Download PDF
          </a>
          {!data?.locked && (
            <button type="button" className="owner-oat-highlight px-3 py-2 text-sm" onClick={lock}>
              Lock month
            </button>
          )}
        </div>
        <p className="text-xs text-zinc-500">Lock month freezes this month&apos;s figures so they stop changing when late costs are entered.</p>
      </div>
    </OwnerShell>
  );
}
