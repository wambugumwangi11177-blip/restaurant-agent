"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import OwnerShell from "@/components/eleven/OwnerShell";
import { posHasLiveData } from "@/lib/posLive";

export default function ElevenSalesDishesPage() {
  const [live, setLive] = useState<boolean | null>(null);

  useEffect(() => {
    posHasLiveData().then(setLive).catch(() => setLive(false));
  }, []);

  return (
    <OwnerShell title="Sales & Dishes">
      {live === null && <p className="text-sm text-zinc-400">Checking POS link…</p>}
      {live === false && (
        <div className="owner-glass-panel space-y-3 rounded-2xl p-4 text-sm leading-6 text-zinc-300">
          <p>Sales and dish mix appear when your POS link goes live.</p>
          <p className="text-zinc-400">
            We do not show placeholder bestsellers or revenue. Connect QuickSell (or your POS webhook), then replay
            receipts from Settings → Till to load sales into Eleven.
          </p>
          <Link href="/eleven/settings/till" className="inline-block text-[var(--accent)] hover:underline">
            Till & POS evidence
          </Link>
        </div>
      )}
      {live === true && (
        <div className="owner-glass-panel space-y-3 rounded-2xl p-4 text-sm leading-6 text-zinc-300">
          <p>POS is sending receipts. Menu engineering and bestsellers use parsed sales — open till evidence to confirm parsing.</p>
          <Link href="/eleven/settings/till" className="inline-block font-semibold text-white hover:underline">
            Open till evidence
          </Link>
          <p className="text-xs text-zinc-500">Ask LEVIII about sales once receipts are parsed into orders.</p>
        </div>
      )}
    </OwnerShell>
  );
}