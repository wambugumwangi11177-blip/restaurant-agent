"use client";

import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import OwnerShell from "@/components/eleven/OwnerShell";
import ExplainedCard from "@/components/eleven/charts/ExplainedCard";
import api from "@/lib/api";
import { formatKes } from "@/lib/formatKes";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

type SawRow = { label: string; value: string };
type DecisionPayload = {
  headline?: string;
  why?: string;
  what_we_saw?: SawRow[];
  usage_sparkline?: { day: string; qty: number }[];
  numbers?: { qty?: string; unit_price_kes?: number; total_kes?: number; amount_kes?: number };
  photo_url?: string | null;
  can_act?: boolean;
  next_step?: string;
  po_draft?: { supplier_name?: string; lines?: { item_name: string; quantity: number; unit: string }[] };
  freshness?: string;
};

export default function DecisionPage() {
  const params = useParams();
  const router = useRouter();
  const kind = String(params.kind);
  const id = String(params.id);
  const [data, setData] = useState<DecisionPayload | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.get(`/api/v1/eleven/decisions/${kind}/${id}`).then((r) => setData(r.data));
  }, [kind, id]);

  useEffect(() => {
    load();
  }, [load]);

  async function decide(decision: "approve" | "decline") {
    setBusy(true);
    try {
      await api.post("/api/v1/store/approvals", { kind, id: Number(id), decision });
      router.push("/eleven");
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  const spark = data?.usage_sparkline ?? [];
  const nums = data?.numbers;

  return (
    <OwnerShell title="Decision">
      <div className="owner-premium-stack">
        <ExplainedCard
          title={kind.replace(/_/g, " ")}
          headline={data?.headline}
          what="What we saw, the numbers, and a photo when one was taken."
          why={data?.why}
          freshness={data?.freshness ?? "Live · from your records"}
          hasData={!!data?.headline}
          emptyHint="Loading decision…"
        >
          <div className="space-y-4">
            {data?.what_we_saw && data.what_we_saw.length > 0 && (
              <div>
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-zinc-400">What we saw</p>
                <ul className="space-y-1 text-sm text-zinc-200">
                  {data.what_we_saw.map((row) => (
                    <li key={row.label} className="flex justify-between gap-2">
                      <span className="text-zinc-400">{row.label}</span>
                      <span>{row.value}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {spark.length > 0 && (
              <div>
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-zinc-400">Use · last 14 days</p>
                <ResponsiveContainer width="100%" height={56}>
                  <BarChart data={spark}>
                    <XAxis dataKey="day" hide />
                    <YAxis hide />
                    <Tooltip />
                    <Bar dataKey="qty" fill="#8b7d72" radius={[2, 2, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
            {nums && (nums.qty || nums.total_kes != null || nums.amount_kes != null) && (
              <div>
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-zinc-400">Numbers</p>
                <ul className="space-y-1 text-sm text-zinc-200">
                  {nums.qty ? <li>{nums.qty}</li> : null}
                  {nums.unit_price_kes != null ? <li>Last price: {formatKes(nums.unit_price_kes)} per unit</li> : null}
                  {nums.total_kes != null ? <li>Total: {formatKes(nums.total_kes)}</li> : null}
                  {nums.amount_kes != null && !nums.total_kes ? <li>At stake: {formatKes(nums.amount_kes)}</li> : null}
                </ul>
              </div>
            )}
            {data?.photo_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={data.photo_url} alt="" className="max-h-40 w-full rounded-xl border border-white/10 object-cover" />
            ) : (
              <p className="text-xs text-zinc-500">No photo attached.</p>
            )}
            {data?.po_draft?.lines?.length ? (
              <div className="rounded-xl border border-white/10 bg-black/20 p-3 text-xs text-zinc-300">
                <p className="font-medium text-zinc-200">PO draft · {data.po_draft.supplier_name}</p>
                {data.po_draft.lines.map((line, i) => (
                  <p key={i}>
                    {line.quantity} {line.unit} {line.item_name}
                  </p>
                ))}
              </div>
            ) : null}
          </div>
        </ExplainedCard>

        {data?.next_step ? <p className="text-sm text-zinc-300">{data.next_step}</p> : null}

        {data?.can_act ? (
          <div className="flex gap-2">
            <button
              type="button"
              disabled={busy}
              className="owner-oat-highlight flex-1 px-4 py-3 text-sm font-medium"
              onClick={() => void decide("approve")}
            >
              Approve
            </button>
            <button
              type="button"
              disabled={busy}
              className="flex-1 rounded-2xl border border-white/25 px-4 py-3 text-sm text-zinc-200"
              onClick={() => void decide("decline")}
            >
              Defer
            </button>
          </div>
        ) : null}
      </div>
    </OwnerShell>
  );
}