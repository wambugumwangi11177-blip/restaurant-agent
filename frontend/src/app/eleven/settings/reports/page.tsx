"use client";

import OwnerShell from "@/components/eleven/OwnerShell";
import { useOwnerGet } from "@/hooks/useOwnerV11";

export default function ReportsSettingsPage() {
  const { data } = useOwnerGet<{ schedule?: { daily?: string; weekly?: string }; past?: { id: string; title: string; href?: string }[] }>("/api/v1/eleven/settings/reports", []);
  return (
    <OwnerShell title="Reports">
      <div className="space-y-3 text-sm">
        <p className="text-zinc-400">Daily {data?.schedule?.daily} · Weekly {data?.schedule?.weekly}</p>
        <ul className="space-y-2">
          {(data?.past ?? []).map((r: { id: string; title: string; href?: string; download?: string }) => (
            <li key={r.id} className="owner-glass-panel flex flex-wrap items-center justify-between gap-2 px-3 py-2">
              <span>{r.title}</span>
              {r.download ? (
                <a className="text-sm underline" href={r.download} download>
                  Download
                </a>
              ) : r.href ? (
                <a className="text-sm underline" href={r.href}>
                  Open
                </a>
              ) : null}
            </li>
          ))}
        </ul>
      </div>
    </OwnerShell>
  );
}