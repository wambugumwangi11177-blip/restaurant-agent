"use client";

import OwnerShell from "@/components/eleven/OwnerShell";
import ExplainedCard from "@/components/eleven/charts/ExplainedCard";
import { useOwnerGet } from "@/hooks/useOwnerV11";
import { formatKes } from "@/lib/formatKes";
import { fmtDay } from "@/lib/chartFormat";
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export default function MoneyBillsPage() {
  const { data } = useOwnerGet<{
    has_sales?: boolean;
    paid?: number;
    due?: number;
    unknown?: number;
    cash_after_bills?: { day: string; after_bills_kes: number }[];
    lowest_after_bills_kes?: number;
    lowest_day?: string;
    lowest_bill_label?: string;
    empty?: string;
  }>("/api/v1/eleven/money/bills", []);

  const series = data?.cash_after_bills ?? [];
  const lowestKes = data?.lowest_after_bills_kes;
  const lowestDay = data?.lowest_day;
  const lowestBill = data?.lowest_bill_label;

  return (
    <OwnerShell title="Bills & cash">
      <div className="owner-premium-stack">
        <ExplainedCard
          title="Bills due"
          headline={`${data?.due ?? 0} due · ${data?.paid ?? 0} paid · ${data?.unknown ?? 0} unknown`}
          what="Running costs your team entered. You approve each payment — nothing is auto-paid."
          freshness="As entered"
          hasData={(data?.due ?? 0) + (data?.paid ?? 0) + (data?.unknown ?? 0) > 0}
          emptyHint={data?.empty ?? "Starts when bills are in Settings."}
        >
          <p className="text-sm text-zinc-300">Open Money for the cash-after-bills trend on the main page.</p>
        </ExplainedCard>

        <ExplainedCard
          title="Cash after bills"
          headline={
            lowestKes != null
              ? `Lowest point: ${formatKes(lowestKes)}${lowestBill ? ` after ${lowestBill}` : ""}`
              : undefined
          }
          sub={lowestDay ? `Running total dipped on ${fmtDay(lowestDay)}` : undefined}
          verdict={
            lowestKes != null && lowestKes < 0
              ? { tone: "bad", text: lowestBill ? `${lowestBill} pushed the running total below zero.` : "Bills pushed the running total below zero." }
              : series.length
                ? { tone: "good", text: "Cash stays above zero in this window." }
                : undefined
          }
          what="Expected cash from sales minus bills already entered, day by day."
          why="Bills only reduce cash on the days they fall due in your records."
          freshness="As entered · bills and sales so far"
          hasData={series.length > 0}
          emptyHint={data?.empty ?? "Starts when bills are in Settings."}
        >
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={series} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <XAxis dataKey="day" tickFormatter={fmtDay} tick={{ fill: "#a1a1aa", fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis hide />
              <Tooltip labelFormatter={(l) => fmtDay(String(l))} formatter={(v) => formatKes(Number(v))} />
              <Line type="monotone" dataKey="after_bills_kes" stroke="#c4b5a8" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </ExplainedCard>
      </div>
    </OwnerShell>
  );
}