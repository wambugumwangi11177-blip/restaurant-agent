"use client";

import Link from "next/link";

export default function OpeningSetupPage() {
  return (
    <section className="owner-glass-panel space-y-3 rounded-3xl p-4">
      <h1 className="text-lg font-semibold">Opening stock per item</h1>
      <p className="text-sm text-zinc-300">
        For each staple: supplier, lead days, usual order quantity, opening count, and a stock photo. Save through the stock list and day photos.
      </p>
      <Link href="/store/stock" className="inline-flex min-h-11 items-center leviii-btn-primary px-4">
        Open stock list
      </Link>
      <Link href="/store/day-photos" className="ml-2 inline-flex min-h-11 items-center px-4 text-sm text-zinc-300 underline">
        Zone photos
      </Link>
    </section>
  );
}