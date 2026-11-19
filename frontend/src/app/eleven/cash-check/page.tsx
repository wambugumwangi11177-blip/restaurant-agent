"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import OwnerShell from "@/components/eleven/OwnerShell";
import { posHasLiveData } from "@/lib/posLive";

export default function ElevenCashCheckPage() {
  const [live, setLive] = useState<boolean | null>(null);

  useEffect(() => {
    posHasLiveData().then(setLive).catch(() => setLive(false));
  }, []);

  return (
    <OwnerShell title="Cash Check">
      {live === null && <p className="text-sm text-zinc-400">Checking POS link…</p>}
      {live === false && (
        <div className="owner-glass-panel space-y-3 rounded-2xl p-4 text-sm leading-6 text-zinc-300">
          <p>Cash check connects when your POS webhook delivers till receipts.</p>
          <p className="text-zinc-400">
            There is no synthetic cash or sales data here. Once QuickSell (or your linked POS) sends receipts,
            you can review them under Settings → Till.
          </p>
          <Link href="/eleven/settings/till" className="inline-block text-[var(--accent)] hover:underline">
            Till & POS evidence
          </Link>
        </div>
      )}
      {live === true && (
        <div className="owner-glass-panel space-y-3 rounded-2xl p-4 text-sm leading-6 text-zinc-300">
          <p>POS receipts are arriving. Open till evidence to replay and match cash movements.</p>
          <Link href="/eleven/settings/till" className="inline-block font-semibold text-white hover:underline">
            Open till evidence
          </Link>
        </div>
      )}
      <p className="mt-4 text-xs text-zinc-500">
        A gap is something to check. It is never proof that a person did something wrong.
      </p>
    </OwnerShell>
  );
}