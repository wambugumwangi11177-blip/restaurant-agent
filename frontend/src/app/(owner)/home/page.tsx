"use client";
// Home — everything the owner needs on one screen (docs/v2/SPEC.md §3.1), from one call: GET /api/v1/owner/home.
//   zone 1  the pulse · zone 2  what is costing you money · health strip · the six areas · zone 4  coming up · zone 5  LEVIII's read
import { useState } from "react";
import { OsError, OsLoading } from "@/components/os/States";
import AreaPanels from "@/components/owner/home/AreaPanels";
import AnswersStrip from "@/components/owner/home/AnswersStrip";
import ComingUp from "@/components/owner/home/ComingUp";
import CostingYouMoney from "@/components/owner/home/CostingYouMoney";
import { FirstWeekBanner, lockedAreas, useFirstWeek } from "@/components/owner/home/FirstWeek";
import HealthStrip from "@/components/owner/home/HealthStrip";
import Pulse from "@/components/owner/home/Pulse";
import InsightNote from "@/components/owner/InsightNote";
import ReadNote from "@/components/owner/home/ReadNote";
import SourceWaiting from "@/components/owner/home/SourceWaiting";
import TargetsOnboarding from "@/components/owner/home/TargetsOnboarding";
import Section from "@/components/owner/Section";
import { useAuth } from "@/context/AuthContext";
import { greeting } from "@/lib/owner/format";
import type { OwnerHome } from "@/lib/owner/types";
import { useOwnerHome } from "@/lib/owner/useOwnerHome";
import { tenantConfig } from "@/lib/tenantConfig";

const PERIODS: { key: OwnerHome["period"]; label: string }[] = [{ key: "today", label: "Today" }, { key: "7d", label: "7 days" }, { key: "30d", label: "30 days" }];

export default function HomePage() {
  const { user } = useAuth();
  const config = tenantConfig(user?.tenant_name);
  const [period, setPeriod] = useState<OwnerHome["period"]>("today");
  const { home, error, reload } = useOwnerHome(period);
  const ageDays = home?.setup?.age_days ?? 999;
  const firstWeek = useFirstWeek(home?.restaurant.id ?? 0, ageDays);

  const waiting = home != null && config.source === "macsoft" && !home.pulse.freshness.source_trusted;

  return (
    <div className="animate-rise-in space-y-10">
      <div className="flex flex-col justify-between gap-5 sm:flex-row sm:items-end">
        <div>
          <p className="mb-1 text-[10px] font-bold uppercase tracking-[0.16em] text-[var(--v-muted-foreground)]">{home?.restaurant.name ?? user?.restaurant_name ?? ""}</p>
          <h1 className="font-display text-[clamp(2rem,4vw,3.2rem)] font-semibold leading-[1.03] tracking-[-0.045em]">{greeting()}<span className="text-[var(--v-primary)]">.</span></h1>
        </div>
        {!waiting && (
          <div role="group" aria-label="Period" className="inline-flex rounded-lg border border-[var(--v-border)] bg-[var(--v-card)] p-1">
            {PERIODS.map((p) => (
              <button key={p.key} type="button" aria-pressed={period === p.key} onClick={() => setPeriod(p.key)}
                className={`min-h-10 rounded-md px-3 text-[11px] font-bold ${period === p.key ? "bg-[var(--v-primary)] text-[var(--v-primary-foreground)]" : "text-[var(--v-muted-foreground)]"}`}>
                {p.label}
              </button>
            ))}
          </div>
        )}
      </div>

      {error && !home && <OsError message="Couldn't reach your restaurant's numbers right now." onRetry={reload} />}
      {!error && !home && <OsLoading />}
      {home && waiting && <SourceWaiting freshness={home.pulse.freshness} />}
      {home && !waiting && (
        <>
          {error && <p role="alert" className="text-xs text-[var(--v-warn)]">Couldn&apos;t refresh just now — showing what we had.</p>}
          <AnswersStrip home={home} />
          <TargetsOnboarding restaurantId={home.restaurant.id} chosen={home.setup?.targets_chosen ?? true} />
          {firstWeek.active && <FirstWeekBanner ageDays={ageDays} onSkip={firstWeek.skip} />}
          <Pulse pulse={home.pulse} period={period} />
          <Section id="costing-you-money" eyebrow="What deserves your attention" title="What's costing you money"><CostingYouMoney data={home.costing_you_money} /></Section>
          <Section id="health" eyebrow="How is each part doing?" title="Your restaurant's health"><HealthStrip health={home.health} /></Section>
          <Section id="areas" eyebrow="Open any part for the detail" title="The six areas"><AreaPanels areas={home.areas} opensOn={firstWeek.active ? lockedAreas(ageDays) : {}} /></Section>
          <Section id="coming-up" eyebrow="Before it surprises you" title="Coming up"><ComingUp data={home.coming_up} /></Section>
          <InsightNote insight={home.insight} />
          <ReadNote read={home.read} />
        </>
      )}
    </div>
  );
}
