"use client";

import OwnerShell from "@/components/eleven/OwnerShell";
import OwnerFeed, { useOwnerFeed } from "@/components/eleven/OwnerFeed";

export default function ActivityPage() {
  const { data, error, refresh } = useOwnerFeed();
  return (
    <OwnerShell title="Activity">
      {!data && !error && <p className="text-sm text-zinc-400">Loading…</p>}
      {error && <p className="text-sm text-red-300">{error}</p>}
      {data && <OwnerFeed data={data} onChanged={refresh} mode="feed" />}
    </OwnerShell>
  );
}
