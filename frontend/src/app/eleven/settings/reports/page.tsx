"use client";

import OwnerShell from "@/components/eleven/OwnerShell";
import ExplainedCard from "@/components/eleven/charts/ExplainedCard";
import { useOwnerGet } from "@/hooks/useOwnerV11";

export default function ReportsSettingsPage() {
  const { data } = useOwnerGet<{ schedule?: { daily?: string; weekly?: string }; past?: { id: string; title: string; href?: string; download?: string }[]; empty?: string }>(
    "/api/v1/eleven/settings/reports",
    [],
  );
  const past = data?.past ?? [];
  const hasSchedule = !!(data?.schedule?.daily || data?.schedule?.weekly);

  return (
    <OwnerShell title="Reports">
      <div className="owner-premium-stack">
        <ExplainedCard
          title="Report schedule"
          headline={hasSchedule ? `Daily ${data?.schedule?.daily} · Weekly ${data?.schedule?.weekly}` : undefined}
          what="When your daily flash and weekly summary are sent — same plain language as Money."
          freshness="As set in Settings"
          hasData={hasSchedule}
          emptyHint="Set delivery times in Settings."
        >
          <p className="text-sm text-zinc-300">Notifications go to the owner inbox when each report is ready.</p>
        </ExplainedCard>

        <ExplainedCard
          title="Past reports"
          headline={past.length ? `${past.length} saved` : undefined}
          what="Download or open earlier daily, weekly, and monthly reports."
          freshness="Archived · from your account"
          hasData={past.length > 0}
          emptyHint={data?.empty ?? "Reports appear after the first scheduled send."}
        >
          <ul className="space-y-2 text-sm">
            {past.map((r) => (
              <li key={r.id} className="owner-glass-inner flex flex-wrap items-center justify-between gap-2 px-3 py-2">
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
        </ExplainedCard>
      </div>
    </OwnerShell>
  );
}