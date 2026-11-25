"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import OwnerShell from "@/components/eleven/OwnerShell";
import ExplainedCard, { type Verdict } from "@/components/eleven/charts/ExplainedCard";
import api from "@/lib/api";
import Link from "next/link";
import { formatKes } from "@/lib/formatKes";

type DecisionPayload = {
  headline?: string;
  why?: string;
  what?: string;
  freshness?: string;
  verdict_tone?: "good" | "watch" | "bad" | "neutral";
  verdict_text?: string;
  photo_url?: string;
  numbers?: { amount_kes?: number };
};

export default function DecisionPage() {
  const params = useParams();
  const kind = String(params.kind);
  const id = String(params.id);
  const [data, setData] = useState<DecisionPayload | null>(null);

  useEffect(() => {
    api.get(`/api/v1/eleven/decisions/${kind}/${id}`).then((r) => setData(r.data));
  }, [kind, id]);

  const amount = data?.numbers?.amount_kes;
  const verdict: Verdict | undefined =
    data?.verdict_text && data?.verdict_tone
      ? { tone: data.verdict_tone, text: data.verdict_text }
      : amount != null && amount >= 10000
        ? { tone: "watch", text: "A sizeable amount — check the evidence before you approve." }
        : data?.headline
          ? { tone: "neutral", text: "Read why and the numbers, then approve or defer." }
          : undefined;

  return (
    <OwnerShell title="Decision">
      <div className="owner-premium-stack">
        <ExplainedCard
          title={`${kind.replace(/_/g, " ")} · ${id}`}
          headline={data?.headline}
          sub={amount != null ? `At stake: ${formatKes(amount)}` : undefined}
          verdict={data ? verdict : undefined}
          what={data?.what ?? "What we saw, the numbers, and a photo when one was taken."}
          why={data?.why}
          freshness={data?.freshness ?? "Live · from your records"}
          hasData={!!data?.headline}
          emptyHint="Loading decision…"
        >
          {data?.photo_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={data.photo_url} alt="" className="max-h-48 w-full rounded-xl border border-white/10 object-cover" />
          ) : (
            <p className="text-sm text-zinc-400">No photo attached.</p>
          )}
        </ExplainedCard>

        <Link href={`/eleven/approvals#${kind}-${id}`} className="owner-oat-highlight inline-block px-3 py-2 text-center text-sm">
          Open approval actions
        </Link>
      </div>
    </OwnerShell>
  );
}