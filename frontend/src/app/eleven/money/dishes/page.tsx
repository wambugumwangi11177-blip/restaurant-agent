"use client";

import OwnerShell from "@/components/eleven/OwnerShell";
import ExplainedCard, { type Verdict } from "@/components/eleven/charts/ExplainedCard";
import { ShareStackedBlock } from "@/components/eleven/v11/ChartBlocks";
import { useOwnerGet } from "@/hooks/useOwnerV11";
import { fmtK } from "@/lib/chartFormat";
import { formatKes } from "@/lib/formatKes";
import { Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from "recharts";

const TICK = { fill: "#a1a1aa", fontSize: 10 };

const CLASS_PLAIN: Record<string, string> = {
  Star: "Sells well & pays well",
  Plowhorse: "Sells well, thin profit",
  Puzzle: "Pays well, sells slowly",
  Dog: "Slow and thin",
};

type QuadPoint = { name?: string; x: number; y: number; class?: string };
type MenuGroup = { key?: string; label: string; count?: number; dishes?: string[] };

function menuGroupsFromApi(
  menu_groups: MenuGroup[] | undefined,
  quad: QuadPoint[],
): MenuGroup[] {
  if (menu_groups?.length) return menu_groups;
  const keys = ["Star", "Plowhorse", "Puzzle", "Dog"] as const;
  return keys.map((key) => {
    const dishes = quad.filter((q) => q.class === key).map((q) => q.name).filter(Boolean) as string[];
    return {
      key,
      label: CLASS_PLAIN[key] ?? key,
      count: dishes.length,
      dishes: dishes.slice(0, 4),
    };
  });
}

export default function DishesMoneyPage() {
  const { data } = useOwnerGet<{
    has_sales?: boolean;
    empty?: string;
    menu_groups?: MenuGroup[];
    quadrant?: QuadPoint[];
    plate_profit?: { name: string; kes: number }[];
    bestsellers?: { name: string; plates: number }[];
    delivery_vs_dine?: { channel: string; kes: number }[];
    suggestions?: { title?: string; detail?: string }[];
  }>("/api/v1/eleven/money/dishes/summary", []);
  const quad = data?.quadrant ?? [];
  const groups = menuGroupsFromApi(data?.menu_groups, quad);
  const stars = quad.filter((q) => q.class === "Star").length;
  const thin = quad.filter((q) => q.class === "Plowhorse" || q.class === "Dog").length;

  const plateProfit = [...(data?.plate_profit ?? [])].sort((a, b) => b.kes - a.kes);
  const topProfit = plateProfit[0];
  const bestsellers = [...(data?.bestsellers ?? [])].sort((a, b) => b.plates - a.plates);
  const topSell = bestsellers[0];

  const delivery = data?.delivery_vs_dine ?? [];
  const dine = delivery.find((d) => /dine|eat/i.test(d.channel))?.kes ?? 0;
  const del = delivery.find((d) => /deliver|take/i.test(d.channel))?.kes ?? delivery.find((d) => d !== delivery[0])?.kes ?? 0;
  const delTotal = delivery.reduce((a, d) => a + d.kes, 0);
  const delPct = delTotal ? Math.round((del / delTotal) * 100) : 0;

  const mapVerdict: Verdict =
    thin > 0
      ? { tone: "watch", text: `${thin} dishes sell a lot but keep little — worth a price or portion check.` }
      : stars > 0
        ? { tone: "good", text: `${stars} dishes sell well and pay well.` }
        : { tone: "neutral", text: "Use the list to spot dogs and puzzles." };

  return (
    <OwnerShell title="Dishes">
      <div className="owner-premium-stack">
        <ExplainedCard
          title="Menu map"
          headline={stars ? `${stars} dishes sell well and pay well` : undefined}
          verdict={data?.has_sales ? mapVerdict : undefined}
          what="Four groups from menu engineering, then each dish on the chart. Further right sells more; higher keeps more per plate."
          why="Popularity is share of plates sold. Profit is price minus recipe cost."
          freshness="Live · from your till and recipes"
          hasData={!!data?.has_sales}
          emptyHint={data?.empty ?? "Starts when dishes sell."}
        >
          <ul className="mb-3 space-y-1.5 text-xs text-zinc-300">
            {groups.map((g) => (
              <li key={g.key ?? g.label} className="flex justify-between gap-2">
                <span>{g.label}</span>
                <span className="shrink-0 text-zinc-500">{g.count ?? g.dishes?.length ?? 0}</span>
              </li>
            ))}
          </ul>
          <ResponsiveContainer width="100%" height={220}>
            <ScatterChart margin={{ top: 8, right: 12, left: 0, bottom: 16 }}>
              <XAxis dataKey="x" name="Popularity" type="number" tick={TICK} axisLine={false} tickLine={false} label={{ value: "Sells more →", position: "insideBottom", offset: -8, fill: "#a1a1aa", fontSize: 10 }} />
              <YAxis dataKey="y" name="Margin %" type="number" width={36} tick={TICK} axisLine={false} tickLine={false} label={{ value: "Keeps more ↑", angle: -90, position: "insideLeft", fill: "#a1a1aa", fontSize: 10 }} />
              <ZAxis range={[40, 40]} />
              <Tooltip cursor={{ strokeDasharray: "3 3" }} formatter={(v, n) => [n === "y" ? `${v}%` : v, n === "x" ? "Popularity" : "Margin"]} labelFormatter={(_, payload) => payload?.[0]?.payload?.name ?? ""} />
              <Scatter data={quad} fill="#c4b5a8" name="Dishes" label={{ dataKey: "name", position: "top", fontSize: 8, fill: "#d4d4d8" }} />
            </ScatterChart>
          </ResponsiveContainer>
        </ExplainedCard>

        <ExplainedCard
          title="Plate profit"
          headline={topProfit ? `${topProfit.name} leaves ${formatKes(topProfit.kes)} on each plate` : undefined}
          verdict={
            topProfit && topProfit.kes < 50
              ? { tone: "watch", text: "Your top seller's plate profit is very thin." }
              : { tone: "neutral", text: "Ranked by contribution margin in the window." }
          }
          what="Menu price minus the recipe's ingredient cost — ranked bars."
          why="Does not include wages or running costs."
          freshness="As entered · from recipes and sales"
          hasData={(plateProfit.length ?? 0) > 0}
          emptyHint={data?.empty ?? "Starts when dishes sell."}
        >
          <ResponsiveContainer width="100%" height={Math.min(44 + plateProfit.length * 28, 220)}>
            <BarChart layout="vertical" data={plateProfit} margin={{ top: 4, right: 48, left: 4, bottom: 0 }}>
              <CartesianGrid horizontal={false} stroke="#3f3f46" strokeDasharray="2 2" />
              <XAxis type="number" hide />
              <YAxis type="category" dataKey="name" width={88} tick={{ ...TICK, fontSize: 9 }} axisLine={false} tickLine={false} />
              <Tooltip formatter={(v) => formatKes(Number(v))} />
              <Bar dataKey="kes" fill="#c4b5a8" radius={[0, 4, 4, 0]}>
                <LabelList dataKey="kes" position="right" formatter={(v: unknown) => fmtK(Number(v))} fill="#e4e4e7" fontSize={10} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ExplainedCard>

        <ExplainedCard
          title="Best sellers"
          headline={topSell ? `${topSell.name} leads, ${topSell.plates} plates` : undefined}
          verdict={{ tone: "neutral", text: "Paid tickets in the menu window." }}
          what="Plates sold — ranked bars. Slow movers sit at the bottom of the list."
          why="The tail is dishes that rarely sold."
          freshness="Live · from your till"
          hasData={(bestsellers.length ?? 0) > 0}
          emptyHint={data?.empty ?? "Starts when dishes sell."}
        >
          <ResponsiveContainer width="100%" height={Math.min(44 + bestsellers.length * 28, 200)}>
            <BarChart layout="vertical" data={bestsellers} margin={{ top: 4, right: 36, left: 4, bottom: 0 }}>
              <XAxis type="number" hide />
              <YAxis type="category" dataKey="name" width={88} tick={{ ...TICK, fontSize: 9 }} axisLine={false} tickLine={false} />
              <Tooltip />
              <Bar dataKey="plates" fill="#8b7d72" radius={[0, 4, 4, 0]}>
                <LabelList dataKey="plates" position="right" fill="#e4e4e7" fontSize={10} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ExplainedCard>

        <ShareStackedBlock
          title="Delivery vs dine-in"
          caption="Paid ticket totals in the last 30 days by how the order was placed."
          slices={delivery.map((d) => ({ name: d.channel, kes: d.kes }))}
          has={(delivery.length ?? 0) > 0}
          empty={data?.empty ?? "Starts when dishes sell."}
          headline={delTotal ? `${formatKes(dine)} dine-in · ${formatKes(del)} delivery (${delPct}% delivery)` : undefined}
          what="A 100% bar of how guests ordered — dine-in, delivery, or other channels."
          why="A jump in delivery share matters if delivery costs more to run."
          freshness="Live · from your till"
        />

        <ul className="space-y-2 text-sm text-zinc-300">
          {(data?.suggestions ?? []).map((s, i) => (
            <li key={i} className="owner-glass-panel px-3 py-2">
              {s.title || s.detail || JSON.stringify(s)}
            </li>
          ))}
        </ul>
      </div>
    </OwnerShell>
  );
}