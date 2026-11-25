"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import OwnerShell from "@/components/eleven/OwnerShell";
import api from "@/lib/api";
import Link from "next/link";

export default function DecisionPage() {
  const params = useParams();
  const kind = String(params.kind);
  const id = String(params.id);
  const [data, setData] = useState<{ headline?: string; why?: string; photo_url?: string; numbers?: { amount_kes?: number } } | null>(null);

  useEffect(() => {
    api.get(`/api/v1/eleven/decisions/${kind}/${id}`).then((r) => setData(r.data));
  }, [kind, id]);

  return (
    <OwnerShell title="Decision">
      <div className="owner-premium-stack text-sm">
        <h2 className="text-lg text-zinc-100">{data?.headline}</h2>
        <p className="text-zinc-300">{data?.why}</p>
        {data?.numbers?.amount_kes != null && <p>At stake: {data.numbers.amount_kes.toLocaleString()} KES</p>}
        {data?.photo_url && <img src={data.photo_url} alt="" className="max-h-48 rounded-xl" />}
        <Link href={`/eleven/approvals#${kind}-${id}`} className="owner-oat-highlight inline-block px-3 py-2">
          Open approval actions
        </Link>
      </div>
    </OwnerShell>
  );
}