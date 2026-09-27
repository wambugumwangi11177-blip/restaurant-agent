"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AlertCircle, Database } from "lucide-react";
import api from "@/lib/api";

type Area = readonly [label: string, value: string, note: string, slug: string];
type Connection = { state?: string; records?: number | null; last_received_at?: string | null; reconciled?: boolean };

const health: Area[] = [
  ["Revenue", "—", "Not available until source data is verified", "revenue"],
  ["Orders", "—", "Not available until source data is verified", "orders"],
  ["Kitchen", "—", "Timing appears after verified delivery", "kitchen"],
  ["Stock", "—", "Not available until source data is verified", "stock"],
  ["Bookings", "—", "Not available until source data is verified", "bookings"],
  ["Team", "—", "Not available until source data is verified", "team"],
];

const money: Area[] = [
  ["Menu & pricing", "—", "Menu and price health", "menu"],
  ["Finance", "—", "Cash and reconciliation", "finance"],
  ["Expenses", "—", "No expense source exists yet", "expenses"],
  ["Suppliers", "—", "Suppliers and purchasing", "suppliers"],
  ["Purchasing", "—", "Purchase orders and commitments", "purchasing"],
  ["Cash reconciliation", "—", "Cash, M-Pesa, and card settlement", "cash-reconciliation"],
];

const growthRisk: Area[] = [
  ["Point of sale", "—", "Sales channels and till activity", "pos"],
  ["Marketing", "—", "Campaigns and guest growth", "marketing"],
  ["Fraud and risk", "—", "Unusual activity and control risks", "risk"],
  ["Notifications", "—", "Important changes and reminders", "notifications"],
];

function AreaCard({ item }: { item: Area }) {
  const [label, value, note, slug] = item;
  return <Link href={`/vibanda/${slug}`} className="block rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-4 transition hover:-translate-y-0.5 hover:border-[var(--v-primary)]/60 focus:outline-none focus:ring-2 focus:ring-[var(--v-primary)]/60">
    <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--v-muted-foreground)]">{label}</p>
    <p className="font-display mt-3 text-2xl font-semibold">{value}</p>
    <p className="mt-2 text-xs text-[var(--v-muted-foreground)]">{note}</p>
    <p className="mt-4 text-[11px] font-semibold text-[var(--v-primary)]">Open {label.toLowerCase()} →</p>
  </Link>;
}

function Section({ eyebrow, title, children }: { eyebrow: string; title: string; children: React.ReactNode }) {
  return <section><p className="mb-1 text-[10px] font-bold uppercase tracking-[0.16em] text-[var(--v-muted-foreground)]">{eyebrow}</p><h2 className="font-display mb-4 text-2xl font-semibold">{title}</h2>{children}</section>;
}

export default function OwnerHomeEmpty({ detail }: { detail: string }) {
  const [connection, setConnection] = useState<Connection | null>(null);
  const [reason, setReason] = useState("Checking the MacSoft connection…");
  useEffect(() => {
    api.get("/api/v1/overview/today?period=today").then((r) => {
      const data = r.data?.data_provenance;
      if (data?.source_connection) setConnection(data.source_connection);
      if (data?.notice) setReason(data.notice);
    }).catch(() => setReason("MacSoft delivery state could not be read."));
  }, []);
  const received = connection?.records == null ? "—" : connection.records.toLocaleString("en-KE");
  const lastDelivery = connection?.last_received_at ? new Date(connection.last_received_at).toLocaleString("en-KE", { timeZone: "Africa/Nairobi", dateStyle: "medium", timeStyle: "short" }) : "—";
  const quality = connection?.reconciled ? "reconciled" : connection?.state === "receiving" ? "not reconciled" : "waiting";
  return <div className="animate-rise-in max-w-5xl space-y-7">
    <div><p className="mb-1 text-[10px] font-bold uppercase tracking-[0.16em] text-[var(--v-muted-foreground)]">Vibanda Village · owner view</p><h1 className="font-display text-[clamp(2rem,4vw,3.25rem)] font-semibold tracking-[-0.045em]">Overview<span className="text-[var(--v-primary)]">.</span></h1><p className="mt-3 text-sm text-[var(--v-muted-foreground)]">{detail}</p></div>
    <div className="flex gap-3 rounded-xl border border-[hsl(43_76%_57_/.45)] bg-[hsl(43_76%_57_/.10)] p-5"><Database className="mt-0.5 shrink-0 text-[var(--v-primary)]" size={22}/><div><p className="font-semibold">Waiting for verified restaurant data</p><p role="status" className="mt-1 text-sm text-[var(--v-muted-foreground)]">{reason}</p><p className="mt-3 text-xs text-[var(--v-muted-foreground)]">Last delivery: {lastDelivery} · Records received: {received} · Data quality: {quality}</p><p className="mt-3 text-xs font-semibold text-[var(--v-primary)]">Next step: ask MarkSoft to send the first test record. We will confirm it here before using it in the owner view.</p></div></div>
    <section className="rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-5"><p className="mb-1 text-[10px] font-bold uppercase tracking-[0.16em] text-[var(--v-muted-foreground)]">Owner briefing</p><h2 className="font-display text-2xl font-semibold">Here is what you need to know</h2><p className="mt-3 text-sm leading-6 text-[var(--v-muted-foreground)]">No business conclusion is available yet because the approved MacSoft source has not delivered a verified record. When it does, this briefing will summarize the few facts, risks, and decisions that matter today.</p><div className="mt-4 grid gap-2 sm:grid-cols-3"><div className="rounded-lg bg-[var(--v-muted)] p-3"><p className="text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--v-muted-foreground)]">Facts</p><p className="mt-2 text-xs text-[var(--v-muted-foreground)]">Confirmed business numbers</p></div><Link href="/vibanda/intelligence" className="rounded-lg bg-[var(--v-muted)] p-3 hover:ring-1 hover:ring-[var(--v-primary)]/60"><p className="text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--v-muted-foreground)]">Attention</p><p className="mt-2 text-xs text-[var(--v-muted-foreground)]">Risks that need review →</p></Link><Link href="/vibanda/data-trust" className="rounded-lg bg-[var(--v-muted)] p-3 hover:ring-1 hover:ring-[var(--v-primary)]/60"><p className="text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--v-muted-foreground)]">Data trust</p><p className="mt-2 text-xs text-[var(--v-muted-foreground)]">Check source confidence →</p></Link></div></section>
    <Section eyebrow="Restaurant health" title="Today at Vibanda Village"><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{health.map((item) => <AreaCard key={item[3]} item={item}/>)}</div></Section>
    <Section eyebrow="Money and control" title="Protect the business"><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{money.map((item) => <AreaCard key={item[3]} item={item}/>)}</div></Section>
    <Section eyebrow="Sales and risk" title="Grow safely"><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{growthRisk.map((item) => <AreaCard key={item[3]} item={item}/>)}</div></Section>
    <Section eyebrow="What changed?" title="Since the last trusted update"><div className="rounded-xl border border-dashed border-[var(--v-border)] px-5 py-7 text-center"><p className="text-sm font-semibold">No changes to compare yet</p><p className="mt-2 text-xs text-[var(--v-muted-foreground)]">This will highlight meaningful movement—not every event—in revenue, service, stock, people, and risk.</p></div></Section>
    <Section eyebrow="Governance and setup" title="Keep the business in control"><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3"><AreaCard item={["Business intelligence", "—", "Decisions and risks", "intelligence"]}/><AreaCard item={["Audit trail", "—", "Changes and approvals", "audit"]}/><AreaCard item={["Restaurant settings", "—", "Profile and connections", "settings"]}/></div></Section>
    <div className="flex gap-3 rounded-xl border border-dashed border-[var(--v-border)] p-5"><AlertCircle className="mt-0.5 shrink-0 text-[var(--v-muted-foreground)]" size={20}/><p className="text-sm text-[var(--v-muted-foreground)]">No local demo or historical operational data is shown. MacSoft remains the system of record.</p></div>
  </div>;
}
