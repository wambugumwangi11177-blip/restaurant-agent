"use client";
// Home — everything the owner needs on one screen (docs/v2/SPEC.md §3.1), from one call: GET /api/v1/owner/home.
//   zone 1  the pulse · zone 2  what is costing you money · health strip · the six areas · zone 4  coming up · zone 5  LEVIII's read
import DailyWorkspace from "@/components/operations/DailyWorkspace";
import DailyOverview from "@/components/owner/home/DailyOverview";
import {useListQuery} from "@/lib/owner/useListQuery";
import Link from "next/link";
import { ArrowRight, ClipboardPen, CookingPot, FileSpreadsheet, PackageCheck } from "lucide-react";
import { OsError, OsLoading } from "@/components/os/States";
import AreaPanels from "@/components/owner/home/AreaPanels";
import ComingUp from "@/components/owner/home/ComingUp";
import CostingYouMoney from "@/components/owner/home/CostingYouMoney";
import { FirstWeekBanner, lockedAreas, useFirstWeek } from "@/components/owner/home/FirstWeek";
import HealthStrip from "@/components/owner/home/HealthStrip";
import Pulse from "@/components/owner/home/Pulse";
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
  const [periodQuery,setPeriod]=useListQuery("period","today");
  const period:OwnerHome["period"]=PERIODS.some(p=>p.key===periodQuery)?periodQuery as OwnerHome["period"]:"today";
  const { home, error, reload, loading } = useOwnerHome(period);
  const ageDays = home?.setup?.age_days ?? 999;
  const firstWeek = useFirstWeek(home?.restaurant.id ?? 0, ageDays);

  const waiting = home != null && config.source === "macsoft" && !home.pulse.freshness.source_trusted;

  return (
    <div className="animate-rise-in space-y-8" aria-busy={loading}>
      <header className="flex flex-wrap items-center justify-between gap-3"><div><p className="leviii-eyebrow">{greeting()} · {home?.restaurant.name??user?.restaurant_name??'Your restaurant'}</p><h1 className="mt-2 font-display text-3xl font-semibold">Your day, at a glance.</h1></div><div className="flex flex-wrap gap-2"><Link href="/entries" className="leviii-primary-button">Record something →</Link><Link href="/explore" className="inline-flex min-h-11 items-center px-3 text-sm font-semibold underline">All tools</Link></div></header>
      {!waiting && <div className="flex flex-wrap items-center justify-between gap-3"><p className="leviii-zone-label !mb-0"><span>01</span> How is today going?</p><div role="group" aria-label="Period" className="inline-flex rounded-xl border border-[var(--v-border)] bg-white p-1">{PERIODS.map(p=><button key={p.key} type="button" aria-pressed={period===p.key} onClick={()=>setPeriod(p.key)} className={`min-h-9 rounded-lg px-4 text-[11px] font-semibold ${period===p.key?"bg-[var(--v-primary)] text-white":"text-[var(--v-muted-foreground)] hover:bg-[var(--v-muted)]"}`}>{p.label}</button>)}</div></div>}


      {home && loading && home.period !== period && <p role="status" className="text-xs text-[var(--v-muted-foreground)]">Updating your view…</p>}
      {error && !home && <OsError message="Couldn't reach your restaurant's numbers right now." onRetry={reload} />}
      {!error && !home && <OsLoading />}
      {home && waiting && <SourceWaiting freshness={home.pulse.freshness} />}
      {home && !waiting && (
        <>
          {error && <p role="alert" className="text-xs text-[var(--v-warn)]">Couldn&apos;t refresh just now — showing what we had.</p>}
          <TargetsOnboarding restaurantId={home.restaurant.id} chosen={home.setup?.targets_chosen ?? true} />
          {firstWeek.active && <FirstWeekBanner ageDays={ageDays} onSkip={firstWeek.skip} />}
          <DailyOverview home={home}/><details className="rounded-xl border border-[var(--v-border)] bg-white p-4"><summary className="min-h-11 cursor-pointer py-2 text-sm font-semibold">Sales trend, break-even & source details</summary><Pulse pulse={home.pulse} period={home.period}/></details>
          <Section id="costing-you-money" eyebrow="What deserves your attention" title="What's costing you money"><CostingYouMoney data={home.costing_you_money} previewLimit={3}/></Section>
          <div className="leviii-workflows" aria-label="Everyday actions">{[
            {href:"/entries",title:"Record the day",note:"Expenses & shift close",icon:ClipboardPen},
            {href:"/planning?tool=forecast-planner",title:"Plan tomorrow",note:"Portions, prep & buying",icon:CookingPot},
            {href:"/planning?tool=stock-review",title:"Check your stock",note:"Value, counts & suppliers",icon:PackageCheck},
            {href:"/reports",title:"See the full picture",note:"Reports & accountant export",icon:FileSpreadsheet},
          ].map(({href,title,note,icon:Icon})=><Link href={href} key={href} className="leviii-workflow"><span><Icon size={19}/></span><div><b>{title}</b><small>{note}</small></div><ArrowRight size={14}/></Link>)}</div>
          <DailyWorkspace compact/>
          <details className="rounded-xl border border-[var(--v-border)] bg-white p-4"><summary className="min-h-11 cursor-pointer py-2 font-semibold">Review the six restaurant areas</summary><section aria-label="Restaurant health details"><h2 className="my-3 text-xl font-semibold">Your restaurant’s health</h2><HealthStrip health={home.health}/></section><Link href="/explore" className="inline-flex min-h-11 items-center text-sm font-semibold underline">Explore every tool →</Link><details><summary className="min-h-11 cursor-pointer py-2 text-sm">All area charts</summary><AreaPanels areas={home.areas} opensOn={firstWeek.active?lockedAreas(ageDays):{}}/></details></details>
          <Section id="coming-up" eyebrow="Before it surprises you" title="Coming up"><ComingUp data={home.coming_up} /></Section>
          <ReadNote read={home.read} />
        </>
      )}
    </div>
  );
}
