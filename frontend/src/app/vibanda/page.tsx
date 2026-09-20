"use client";
// Vibanda Village — HOME = "Overview Today", restyled to the approved sketch:
// eyebrow labels (10px bold uppercase tracking-[0.16em]), font-display serif
// headings, rounded-xl cards on translucent card surface, teal primary,
// gold accents, sketch section order (6 cards → attention → pulse →
// parts → performance).
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ChevronRight, TrendingUp } from "lucide-react";
import api from "@/lib/api";
import { fmtKes, fmtPct, greetingFor } from "@/lib/format";
import { OsLoading, OsEmpty, OsError } from "@/components/os/States";
import PartHealth from "@/components/vibanda/PartHealth";
import { useAuth } from "@/context/AuthContext";

type Feed = {
  greeting_date: string;
  restaurant_name: string;
  period: string;
  unavailable_metrics: string[];
  revenue: { revenue: number; orders: number; avg_order: number; pace_projection: number };
  orders: { revenue: number; orders: number; delayed: number; active_now: number; split: Record<string, number> };
  kitchen: { avg_prep_min: number; delay_risk: number; bottleneck: string | null };
  stock: { low_stock: { name: string; qty: number }[]; expiring_48h: string[]; waste_pct_week: number };
  bookings: { covers_today: number; next_reservation_min: number | null; waitlist: number; no_show_pct: number };
  staff: { scheduled: number; on_shift: number; overtime_risk: number; labor_cost_pct: number };
  attention: {
    id: string; domain: string; title: string; why: string; what_to_do: string;
    impact: string; status: string;
    // Present only on cards produced by the decision layer. An operational
    // alert ("Beef is running low") is a fact and carries neither: it is not an
    // inference, so a trust % on it would be theatre.
    priority_score?: number;
    confidence_pct?: number;
  }[];
  pulse: { domain: string; headline: string; detail: string }[];
  performance: { revenue_trend: { date: string; revenue: number; orders: number }[] };
};

const PERIODS = ["1h", "today", "7d", "30d"] as const;
const PERIOD_LABEL: Record<string, string> = { "1h": "1H", today: "Today", "7d": "7D", "30d": "30D" };

// Sketch pattern: eyebrow + font-display heading per section
function SectionHead({ eyebrow, title, meta }: { eyebrow: string; title: string; meta?: string }) {
  return (
    <div className="mb-4 flex items-end justify-between">
      <div>
        <p className="mb-1 text-[10px] font-bold uppercase tracking-[0.16em] text-[var(--v-muted-foreground)]">{eyebrow}</p>
        <h2 className="font-display text-2xl font-semibold tracking-[-0.035em]">{title}</h2>
      </div>
      {meta && <span className="hidden text-[10px] text-[var(--v-muted-foreground)] sm:block">{meta}</span>}
    </div>
  );
}

// Sketch pillar card: min-h-[190px], translucent card, icon chip.
//
// NOT a navigation target. The whole card used to be one big <button> that
// jumped to /vibanda/os — so on Home, pressing anything took you to the OS
// page. Home is where the system reports to you; OS is where you question it.
// The card now just reports, and carries one small, explicit "Ask" affordance
// for the moment you actually want to go and ask.
function PillarCard({ label, primaryLabel, primary, comparison, signals, askLabel, onAsk }: {
  label: string; primaryLabel: string; primary: string; comparison: string;
  signals: string[]; askLabel: string; onAsk: () => void;
}) {
  return (
    <article className="group flex min-h-[190px] flex-col justify-between rounded-xl border border-[var(--v-border)] bg-[hsl(42_40%_99_/_0.72)] p-4 text-left transition-all hover:border-[hsl(201_47%_29_/_0.38)] hover:bg-[var(--v-card)]">
      <div>
        <span className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.12em] text-[var(--v-muted-foreground)]">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-[var(--v-muted)] text-[var(--v-primary)]">
            <TrendingUp size={14} />
          </span>
          {label}
        </span>
        <p className="mt-5 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--v-muted-foreground)]">{primaryLabel}</p>
        <p className="font-display mt-1 text-[1.55rem] font-semibold tracking-[-0.035em]">{primary}</p>
      </div>
      <div className="mt-4 space-y-1.5">
        {comparison && <p className="text-[11px] font-semibold text-[var(--v-primary)]">{comparison}</p>}
        {signals.map((s) => (
          <p key={s} className="text-[10px] text-[var(--v-muted-foreground)]">{s}</p>
        ))}
        <button
          type="button"
          onClick={onAsk}
          className="mt-2 inline-flex min-h-8 items-center gap-1 rounded-lg border border-[var(--v-border)] px-2 py-1 text-[10px] font-bold text-[var(--v-primary)] opacity-80 transition-all hover:border-[hsl(201_47%_29_/_0.45)] hover:bg-[var(--v-muted)] hover:opacity-100"
        >
          {askLabel} <ChevronRight size={11} />
        </button>
      </div>
    </article>
  );
}

// How much the system trusts its own recommendation.
//
// Shown ONLY on cards the decision layer produced. An operational alert is a
// measured fact — the beef really is below its reorder point — and putting a
// percentage on it would imply doubt that does not exist. A recommendation is
// an inference, and the owner deserves to know whether it is a near-certainty
// or a hunch before acting on it.
//
// The number is the agent's own confidence, already scaled by that agent's
// recent forecast accuracy (ai/decisions/__init__.py::_apply_reliability), so
// an agent that has been getting it wrong reports lower confidence here.
function ConfidenceChip({ pct }: { pct: number }) {
  const band =
    pct >= 75 ? { label: "high confidence", tone: "var(--v-good)" }
    : pct >= 50 ? { label: "moderate confidence", tone: "var(--v-primary)" }
    : { label: "low confidence", tone: "var(--v-muted-foreground)" };
  return (
    <span
      className="text-[10px] font-semibold"
      style={{ color: band.tone }}
      title={`The system is ${pct}% confident in this recommendation, adjusted for how accurate this agent has been recently. Not a guarantee.`}
    >
      {pct}% · {band.label}
    </span>
  );
}

// Sketch attention card: icon square, source · impact row, Why/What-to-do
// grid under a top border, action buttons.
function AttentionCard({ card, onDecide, onAsk }: {
  card: Feed["attention"][number];
  onDecide: (id: string, d: "approved" | "later" | "rejected") => Promise<void>;
  onAsk: (question: string) => void;
}) {
  const [saving, setSaving] = useState(false);
  const [decisionError, setDecisionError] = useState(false);
  const recordDecision = async (decision: "approved" | "later" | "rejected") => {
    if (saving) return;
    setSaving(true);
    setDecisionError(false);
    try {
      await onDecide(card.id, decision);
    } catch {
      setDecisionError(true);
    } finally {
      setSaving(false);
    }
  };
  return (
    <article className="rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-4 transition-shadow hover:shadow-[0_10px_30px_hsl(201_47%_29_/.05)] sm:p-5">
      <div className="flex items-start gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[hsl(42_71%_75_/_0.62)] text-[var(--v-primary)]">
          <TrendingUp size={17} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--v-muted-foreground)]">{card.domain}</span>
            {card.impact && <span className="h-1 w-1 rounded-full bg-[var(--v-border)]" />}
            {card.impact && <span className="text-[10px] font-semibold text-[var(--v-primary)]">{card.impact}</span>}
            {typeof card.confidence_pct === "number" && (
              <>
                <span className="h-1 w-1 rounded-full bg-[var(--v-border)]" />
                <ConfidenceChip pct={card.confidence_pct} />
              </>
            )}
          </div>
          <h3 className="mt-2 text-sm font-bold leading-snug">{card.title}</h3>
        </div>
      </div>
      <div className="ml-12 mt-4 grid gap-3 border-t border-[var(--v-border)] pt-4 sm:grid-cols-2">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--v-muted-foreground)]">Why</p>
          <p className="mt-1 text-xs leading-relaxed text-[hsl(208_29%_19_/_0.72)]">{card.why}</p>
        </div>
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--v-muted-foreground)]">What to do</p>
          <p className="mt-1 text-xs leading-relaxed text-[hsl(208_29%_19_/_0.72)]">{card.what_to_do}</p>
        </div>
      </div>
      <div className="ml-12 mt-4 flex flex-wrap items-center gap-2">
        <button disabled={saving} onClick={() => recordDecision("approved")}
          className="min-h-9 rounded-lg bg-[var(--v-primary)] px-3 py-2 text-[10px] font-bold text-[var(--v-primary-foreground)] hover:brightness-105">Approve</button>
        <button disabled={saving} onClick={() => recordDecision("later")}
          className="min-h-10 rounded-lg border border-[var(--v-border)] px-2 py-2 text-[11px] font-bold hover:bg-[var(--v-muted)]">Later</button>
        <button disabled={saving} onClick={() => recordDecision("rejected")}
          className="min-h-10 rounded-lg border border-[var(--v-border)] px-2 py-2 text-[11px] font-bold hover:bg-[var(--v-muted)]">Reject</button>
        <button
          onClick={() => onAsk(card.title)}
          className="min-h-10 rounded-lg border border-[hsl(201_47%_29_/_0.45)] px-2 py-2 text-[11px] font-bold text-[var(--v-primary)] hover:bg-[var(--v-muted)]">
          Ask AI about this
        </button>
      </div>
      <p className="ml-12 mt-2 text-xs text-[var(--v-muted-foreground)]">
        Records your decision only. Apply operational changes in your source system.
      </p>
      {decisionError && <p role="alert" className="ml-12 mt-2 text-xs text-[var(--v-warn)]">
        Your decision could not be saved. Please try again.
      </p>}
    </article>
  );
}

export default function VibandaHomePage() {
  const { user } = useAuth();
  const router = useRouter();
  const [feed, setFeed] = useState<Feed | null>(null);
  const [err, setErr] = useState(false);
  const [period, setPeriod] = useState("today");
  const [dailyReport, setDailyReport] = useState<string | null>(null);
  const [showReport, setShowReport] = useState(false);

  const load = useCallback((p: string) => {
    setErr(false);
    api.get<Feed>(`/api/v1/overview/today?period=${p}`)
      .then((r) => setFeed(r.data))
      .catch(() => setErr(true));
  }, []);

  useEffect(() => { load(period); }, [period, load]);
  useEffect(() => {
    api.get("/api/v1/reports/daily?narrate=false").then((r) => setDailyReport(r.data.report_text)).catch(() => {});
  }, []);

  const decide = async (cardId: string, decision: "approved" | "later" | "rejected") => {
    await api.post(`/api/v1/overview/attention/${encodeURIComponent(cardId)}/decision`, { decision });
    setFeed((f) => f && { ...f, attention: f.attention.filter((c) => c.id !== cardId) });
  };

  const firstName = (user?.restaurant_name || "").split(" ")[0];
  const hour = new Date().getHours();
  const greeting = greetingFor(hour);
  const ask = (q: string) => router.push(`/vibanda/os?q=${encodeURIComponent(q)}`);

  return (
    <div className="animate-rise-in space-y-10">
      {/* Hero — sketch pattern: eyebrow date (in layout), big display heading
          with primary-colored period, context subtitle */}
      <div className="mb-8 flex flex-col justify-between gap-5 sm:flex-row sm:items-end">
        <div>
          <h1 className="font-display text-[clamp(2rem,4vw,3.2rem)] font-semibold leading-[1.03] tracking-[-0.045em]">
            {greeting}
            {firstName ? `, ${firstName}` : ""}
            <span className="text-[var(--v-primary)]">.</span>
          </h1>
          <p className="mt-3 max-w-xl text-sm text-[var(--v-muted-foreground)]">
            {feed
              ? <>Here&apos;s what deserves your attention at <b>{feed.restaurant_name}</b> — the full picture lives in Overview Today below.</>
              : "Loading your restaurant…"}
          </p>
        </div>
        {/* Sketch period control: bordered pill group */}
        <div className="inline-flex rounded-lg border border-[var(--v-border)] bg-[hsl(42_40%_99_/_0.68)] p-1">
          {PERIODS.map((p) => (
            <button key={p} onClick={() => setPeriod(p)}
              className={`min-h-8 rounded-md px-3 text-[10px] font-bold transition-colors ${
                period === p
                  ? "bg-[var(--v-primary)] text-[var(--v-primary-foreground)]"
                  : "text-[var(--v-muted-foreground)]"
              }`}>
              {PERIOD_LABEL[p]}
            </button>
          ))}
        </div>
      </div>
      <p className="flex items-center gap-2 rounded-lg border border-[var(--v-border)] bg-[hsl(42_40%_99_/_0.55)] px-3 py-2 text-[10px] text-[var(--v-muted-foreground)]">
        <span className="flex h-4 w-4 items-center justify-center rounded-full bg-[var(--v-accent)] text-[var(--v-accent-foreground)]">i</span>
        Prototype data · live POS sync coming soon
      </p>

      {err && <OsError message="Couldn't reach the kitchen right now." onRetry={() => load(period)} />}
      {!err && !feed && <OsLoading />}
      {!err && feed && (
        <>
          {/* Today snapshot — 6 pillar cards */}
          <section aria-labelledby="snapshot-heading">
            <SectionHead eyebrow="How are we doing?" title="Today at Vibanda Village"
              meta="Operational cards stay current · period sets context" />
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              <PillarCard label="Revenue" primaryLabel={`Revenue · ${PERIOD_LABEL[period]}`} primary={fmtKes(feed.revenue.revenue)}
                comparison={feed.revenue.orders ? `Average order · ${fmtKes(feed.revenue.avg_order)}` : ""}
                signals={[
                  feed.revenue.pace_projection ? `On pace for ~${fmtKes(feed.revenue.pace_projection)} today` : (feed.revenue.orders ? "Paid, non-cancelled orders · no forecast available" : "No paid sales recorded in this period"),
                ]}
                askLabel="Ask about sales" onAsk={() => ask("How are my sales today?")} />
              <PillarCard label="Orders" primaryLabel={`Orders · ${PERIOD_LABEL[period]}`} primary={`${feed.orders.orders} orders`}
                comparison={feed.orders.active_now ? `${feed.orders.active_now} active now` : ""}
                signals={[Object.entries(feed.orders.split).filter(([, v]) => v > 0).map(([k, v]) => `${v} ${k.replace("_", "-")}`).join(" · ") || "—"]}
                askLabel="Ask about orders" onAsk={() => ask("Are there any delayed orders?")} />
              <PillarCard label="Kitchen" primaryLabel="Kitchen" primary={feed.unavailable_metrics.includes("kitchen") ? "Not available" : `${feed.kitchen.avg_prep_min} min prep`}
                comparison={feed.kitchen.delay_risk ? `${feed.kitchen.delay_risk} orders approaching delay` : ""}
                signals={[feed.unavailable_metrics.includes("kitchen") ? "Prep times and delays have not been verified" : (feed.kitchen.bottleneck ? `Bottleneck: ${feed.kitchen.bottleneck}` : "No bottleneck recorded")]}
                askLabel="Ask about the kitchen" onAsk={() => ask("Is the kitchen running behind?")} />
              <PillarCard label="Stock" primaryLabel="Stock" primary={feed.stock.low_stock.length ? `${feed.stock.low_stock.length} to watch` : "No low-stock alerts"}
                comparison={feed.stock.low_stock[0] ? `${feed.stock.low_stock[0].name} at or below reorder point` : ""}
                signals={feed.stock.low_stock.slice(0, 2).map((i) => `${i.name} · ${i.qty} left`)}
                askLabel="Ask about stock" onAsk={() => ask("What am I about to run out of?")} />
              <PillarCard label="Bookings" primaryLabel="Covers expected" primary={`${feed.bookings.covers_today} covers`}
                comparison={feed.bookings.next_reservation_min ? `Next reservation in ${feed.bookings.next_reservation_min} min` : ""}
                signals={[feed.unavailable_metrics.includes("waitlist") ? "Waitlist data not available" : `${feed.bookings.waitlist} tables on the waitlist`]}
                askLabel="Ask about bookings" onAsk={() => ask("Who's booked tonight?")} />
              <PillarCard label="Staff" primaryLabel="Coverage" primary={`${feed.staff.scheduled} scheduled`}
                comparison={feed.staff.overtime_risk ? `${feed.staff.overtime_risk} overtime risk` : ""}
                signals={[feed.staff.labor_cost_pct ? `Labor cost · ${fmtPct(feed.staff.labor_cost_pct)}` : "—"]}
                askLabel="Ask about staff" onAsk={() => ask("Who worked the most shifts this week?")} />
            </div>
          </section>

          {/* What needs your attention */}
          <section aria-labelledby="attention-heading">
            <SectionHead eyebrow="Decision support" title="What needs your attention"
              meta={feed.attention.length ? `${feed.attention.length} high-priority ${feed.attention.length === 1 ? "item" : "items"}` : undefined} />
            <div className="space-y-3">
              {feed.attention.length === 0 && (
                <div className="rounded-xl border border-[hsl(150_28%_41_/_0.24)] bg-[hsl(150_28%_41_/_0.06)] px-5 py-8 text-center sm:px-10">
                  <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full bg-[hsl(150_28%_41_/_0.12)] text-[var(--v-good)]">✓</div>
                  <h3 className="font-display mt-3 text-xl font-semibold tracking-[-0.02em]">No open attention cards</h3>
                  <p className="mx-auto mt-1.5 max-w-md text-xs text-[var(--v-muted-foreground)]">
                    No open cards were returned. This does not confirm that every restaurant area has been checked.
                  </p>
                </div>
              )}
              {feed.attention.map((c) => (
                <AttentionCard key={c.id} card={c} onDecide={decide} onAsk={ask} />
              ))}
            </div>
          </section>

          {/* Operational pulse */}
          {feed.pulse.length > 0 && (
            <section aria-labelledby="pulse-heading">
              <SectionHead eyebrow="What's happening right now?" title="Operational pulse"
                meta="Current context · refreshed just now" />
              <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                {feed.pulse.map((p) => (
                  <div key={p.domain + p.headline}
                    className="flex min-h-[88px] items-start gap-3 rounded-lg border border-[var(--v-border)] bg-[hsl(42_40%_99_/_0.48)] p-3.5 text-left">
                    <span className="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--v-good)]" />
                    <span className="min-w-0">
                      <strong className="block text-[11px] leading-snug">{p.domain}</strong>
                      <span className="mt-1 block text-[11px] font-semibold text-[hsl(208_29%_19_/_0.78)]">{p.headline}</span>
                      <small className="mt-1 block text-[10px] text-[var(--v-muted-foreground)]">{p.detail}</small>
                    </span>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* How each part is doing */}
          <PartHealth />

          {/* Business performance */}
          <section aria-labelledby="performance-heading" className="mt-10 rounded-xl border border-[var(--v-border)] bg-[hsl(42_40%_99_/_0.55)] p-4 sm:p-5">
            <div className="mb-4 flex items-end justify-between">
              <div>
                <p className="mb-1 text-[10px] font-bold uppercase tracking-[0.16em] text-[var(--v-muted-foreground)]">Deeper context</p>
                <h2 id="performance-heading" className="font-display text-2xl font-semibold tracking-[-0.035em]">Business performance</h2>
                <p className="mt-1.5 text-xs text-[var(--v-muted-foreground)]">Enough context to know if the business is okay. Open a module when you need the why.</p>
              </div>
              <button onClick={() => ask("How is my restaurant performing?")}
                className="inline-flex min-h-9 items-center gap-1.5 self-start rounded-lg border border-[var(--v-border)] px-3 py-2 text-[10px] font-bold text-[var(--v-primary)] hover:border-[hsl(201_47%_29_/_0.45)] hover:bg-[var(--v-muted)]">
                Ask AI about performance <ChevronRight size={13} />
              </button>
            </div>
            {/* Sketch: 7-day bars */}
            <div className="flex h-24 items-end gap-1.5">
              {(() => {
                const trend = feed.performance.revenue_trend;
                const max = Math.max(...trend.map((t) => t.revenue), 1);
                return trend.map((t) => (
                  <div key={t.date} className="flex min-w-0 flex-1 flex-col items-center gap-1.5"
                    title={`${t.date}: ${fmtKes(t.revenue)} · ${t.orders} orders`}>
                    <div className="flex h-20 w-full items-end">
                      <div className="w-full rounded-t-md bg-[hsl(201_47%_29_/_0.75)] transition-all hover:bg-[var(--v-primary)]"
                        style={{ height: `${Math.max((t.revenue / max) * 100, 3)}%` }} />
                    </div>
                    <span className="truncate text-[9px] text-[var(--v-muted-foreground)]">{t.date.slice(5)}</span>
                  </div>
                ));
              })()}
            </div>
            {dailyReport && (
              <div className="mt-4 border-t border-[var(--v-border)] pt-4">
                <button onClick={() => setShowReport((s) => !s)}
                  className="flex w-full items-center justify-between text-left text-[11px] font-bold uppercase tracking-[0.14em] text-[var(--v-muted-foreground)]">
                  <span>Daily report · drafted from your data</span>
                  <span>{showReport ? "Hide" : "Show"}</span>
                </button>
                {showReport && <pre className="mt-3 whitespace-pre-wrap font-sans text-[12px] leading-relaxed text-[hsl(208_29%_19_/_0.82)]">{dailyReport}</pre>}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
