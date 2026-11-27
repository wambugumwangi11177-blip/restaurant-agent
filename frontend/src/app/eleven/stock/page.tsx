"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import OwnerShell from "@/components/eleven/OwnerShell";
import ExplainedCard, { type Verdict } from "@/components/eleven/charts/ExplainedCard";
import { useOwnerGet } from "@/hooks/useOwnerV11";
import api from "@/lib/api";
import { fmtDay, fmtK } from "@/lib/chartFormat";
import { formatKes } from "@/lib/formatKes";
import { plural } from "@/lib/pluralize";
import { Bar, BarChart, CartesianGrid, LabelList, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

const TICK = { fill: "#a1a1aa", fontSize: 10 };

export default function ElevenStockPage() {
  type Row = {
    name: string;
    on_hand: number;
    days_left?: number | null;
    days_label?: string;
    status: string;
    unit?: string;
  };
  const { data: levels } = useOwnerGet<{ rows?: Row[]; has_data?: boolean; empty?: string }>("/api/v1/eleven/stock/levels", []);
  const { data: reorder } = useOwnerGet<{ rows?: { id: number; item: string; kes: number }[]; has_data?: boolean; empty?: string }>(
    "/api/v1/eleven/stock/reorder",
    [],
  );
  const { data: missing } = useOwnerGet<{
    issued_kg?: number;
    used_kg?: number;
    gap_kg?: number;
    kes_risk?: number;
    item_name?: string;
    photo_url?: string;
    has_data?: boolean;
    empty?: string;
  }>("/api/v1/eleven/stock/missing", []);
  const { data: trend } = useOwnerGet<{ points?: { day: string; qty: number }[]; has_data?: boolean; empty?: string }>(
    "/api/v1/eleven/stock/use-trend",
    [],
  );
  const { data: waste } = useOwnerGet<{ bars?: { reason: string; kes: number }[]; has_data?: boolean; empty?: string }>(
    "/api/v1/eleven/stock/waste",
    [],
  );
  const [missingPhoto, setMissingPhoto] = useState<string | null>(null);

  useEffect(() => {
    if (!missing?.photo_url) {
      setMissingPhoto(null);
      return;
    }
    let active = true;
    api
      .get(missing.photo_url, { responseType: "blob" })
      .then((r) => {
        if (!active) return;
        setMissingPhoto(URL.createObjectURL(r.data));
      })
      .catch(() => active && setMissingPhoto(null));
    return () => {
      active = false;
    };
  }, [missing?.photo_url]);

  const levelRows = levels?.rows ?? [];
  const tightest = useMemo(() => {
    const sorted = [...levelRows].sort((a, b) => (a.days_left ?? 999) - (b.days_left ?? 999));
    return sorted[0];
  }, [levelRows]);

  const levelsVerdict: Verdict | undefined = tightest
    ? tightest.status === "red"
      ? { tone: "bad", text: `${tightest.name} is below par or inside lead time.` }
      : tightest.status === "amber"
        ? { tone: "watch", text: `${tightest.name} is getting low.` }
        : { tone: "good", text: "Stock is within par on the items counted." }
    : undefined;

  const reorderRows = reorder?.rows ?? [];
  const wasteBars = useMemo(() => [...(waste?.bars ?? [])].sort((a, b) => b.kes - a.kes), [waste?.bars]);
  const wasteTop = wasteBars[0];
  const wasteTotal = wasteBars.reduce((a, b) => a + b.kes, 0);

  const issued = missing?.issued_kg ?? 0;
  const used = missing?.used_kg ?? 0;
  const gap = missing?.gap_kg ?? 0;
  const kesRisk = missing?.kes_risk ?? 0;
  const missingVerdict: Verdict | undefined =
    gap > 0
      ? kesRisk >= 5000
        ? { tone: "bad", text: "The gap is large enough to check today." }
        : { tone: "watch", text: "More was used than issued — worth a count." }
      : { tone: "good", text: "Issued and used are in line." };

  const trendPts = trend?.points ?? [];
  const trendTotal = trendPts.reduce((a, p) => a + p.qty, 0);

  return (
    <OwnerShell title="Stock">
      <div className="owner-premium-stack">
        <ExplainedCard
          title="Stock levels"
          headline={tightest ? `${tightest.name} has about ${tightest.days_label ?? "no use yet"}` : undefined}
          sub={tightest ? `${tightest.on_hand} ${tightest.unit ?? "units"} on hand` : undefined}
          verdict={levelsVerdict}
          what="Each line is on hand and days left at today's use rate. Sorted tightest first. Green is OK, amber is low, red is critical."
          why="Days left = on hand ÷ usual use per day. Par is enough until the next delivery."
          freshness="As entered · from Jack's counts"
          hasData={!!levels?.has_data}
          emptyHint={levels?.empty ?? "Starts when Jack counts stock."}
        >
          <ul className="max-h-44 space-y-1.5 overflow-y-auto text-xs">
            {[...levelRows].sort((a, b) => (a.days_left ?? 999) - (b.days_left ?? 999)).map((r) => (
              <li key={r.name} className="flex justify-between gap-2">
                <span className={r.status === "red" ? "text-red-300" : r.status === "amber" ? "text-amber-200" : "text-zinc-200"}>
                  {r.name}
                </span>
                <span className="shrink-0 text-zinc-300">
                  {r.on_hand} {r.unit ?? "units"} · {r.days_label ?? (r.days_left != null ? `${r.days_left}d` : "no use yet")}
                </span>
              </li>
            ))}
          </ul>
        </ExplainedCard>

        <ExplainedCard
          title="Reorder list"
          headline={reorderRows.length ? `${plural(reorderRows.length, "item")} to reorder` : undefined}
          verdict={
            reorderRows.length
              ? { tone: "watch", text: "Approve before any line hits lead time." }
              : undefined
          }
          what="Qty uses per day × supplier lead time. You approve; nothing is ordered by itself."
          why="Draft POs wait for your approval and route to whoever orders."
          freshness="As entered · from counts and lead times"
          hasData={!!reorder?.has_data}
          emptyHint={reorder?.empty ?? "Starts when stock runs low."}
        >
          <ul className="space-y-1 text-xs text-zinc-300">
            {reorderRows.map((r) => (
              <li key={r.id} className="flex justify-between gap-2">
                <span>{r.item}</span>
                <span className="text-zinc-400">{formatKes(r.kes)}</span>
              </li>
            ))}
          </ul>
        </ExplainedCard>

        <ExplainedCard
          title="Missing stock"
          headline={
            missing?.has_data
              ? `${missing.item_name ?? "Stock"}: ${gap} kg missing (~${formatKes(kesRisk)})`
              : undefined
          }
          sub={missing?.has_data ? `Issued ${issued} kg · used ${used} kg` : undefined}
          verdict={missing?.has_data ? missingVerdict : undefined}
          what="Issued to the kitchen vs what recipes say should have been used on paid tickets. Photo from the last count when there is a gap."
          why="The gap is waste, over-portioning, or stock that was not recorded."
          freshness="As entered · from issues and the till"
          hasData={!!missing?.has_data}
          emptyHint={missing?.empty ?? "Starts when kitchen issues and sales move stock."}
        >
          <ResponsiveContainer width="100%" height={100}>
            <BarChart
              data={[
                { name: "Issued", kg: issued },
                { name: "Used", kg: used },
              ]}
              margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
            >
              <XAxis dataKey="name" tick={TICK} axisLine={false} tickLine={false} />
              <YAxis hide />
              <Tooltip formatter={(v) => `${v} kg`} />
              <Bar dataKey="kg" fill="#8b7d72" radius={[4, 4, 0, 0]}>
                <LabelList dataKey="kg" position="top" fill="#e4e4e7" fontSize={10} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          {missingPhoto ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={missingPhoto} alt="Stock count evidence" className="mt-2 max-h-28 rounded-xl border border-white/10" />
          ) : null}
        </ExplainedCard>

        <ExplainedCard
          title="Use trend"
          headline={trendPts.length ? `${Math.round(trendTotal)} units issued in ${trendPts.length} days` : undefined}
          what="Kitchen issues over the last month — each point is one day."
          why="A steady climb may mean higher sales; a sudden drop may mean counts were missed."
          freshness="As entered · from kitchen issues"
          hasData={!!trend?.has_data}
          emptyHint={trend?.empty ?? "Starts when kitchen uses stock."}
        >
          <ResponsiveContainer width="100%" height={120}>
            <LineChart data={trendPts} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <XAxis dataKey="day" tickFormatter={fmtDay} tick={TICK} axisLine={false} tickLine={false} interval="preserveStartEnd" />
              <YAxis hide />
              <Tooltip labelFormatter={(l) => fmtDay(String(l))} />
              <Line type="monotone" dataKey="qty" stroke="#c4b5a8" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </ExplainedCard>

        <ExplainedCard
          title="Waste"
          headline={wasteTop ? `${wasteTop.reason} is the largest share (${formatKes(wasteTop.kes)})` : undefined}
          sub={wasteTotal ? `${formatKes(wasteTotal)} logged` : undefined}
          verdict={wasteTop && wasteTotal && wasteTop.kes / wasteTotal > 0.5 ? { tone: "watch", text: "One reason dominates — worth a team chat." } : { tone: "neutral", text: "Reasons are spread across the period." }}
          what="Ranked bars in KES — reasons logged when stock was marked waste."
          why="Waste pushes up your ingredient share of sales."
          freshness="As entered · from store logs"
          hasData={!!waste?.has_data}
          emptyHint={waste?.empty ?? "Starts when waste is logged."}
        >
          <ResponsiveContainer width="100%" height={Math.min(44 + wasteBars.length * 28, 200)}>
            <BarChart layout="vertical" data={wasteBars} margin={{ top: 4, right: 48, left: 4, bottom: 0 }}>
              <CartesianGrid horizontal={false} stroke="#3f3f46" strokeDasharray="2 2" />
              <XAxis type="number" hide />
              <YAxis type="category" dataKey="reason" width={72} tick={TICK} axisLine={false} tickLine={false} />
              <Tooltip formatter={(v) => formatKes(Number(v))} />
              <Bar dataKey="kes" fill="#8b7d72" radius={[0, 4, 4, 0]}>
                <LabelList dataKey="kes" position="right" formatter={(v: unknown) => fmtK(Number(v))} fill="#e4e4e7" fontSize={10} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ExplainedCard>

        <div className="flex gap-2">
          <Link href="/eleven/stock/suppliers" className="owner-oat-highlight flex-1 px-3 py-3 text-center text-sm">
            Suppliers
          </Link>
          <Link href="/eleven/stock/prep" className="owner-oat-highlight flex-1 px-3 py-3 text-center text-sm">
            Prep
          </Link>
        </div>
      </div>
    </OwnerShell>
  );
}