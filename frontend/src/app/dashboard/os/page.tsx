"use client";
// Restaurant OS — HOME. Sketch parity: greeting hero, 1H|Today|7D|30D toggle,
// 6 KPI cards, attention cards with Approve/Later/Reject/Ask-AI, pulse,
// 7-day performance. User-centered contract: answer first, owner's language.
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/api";
import { fmtKes, fmtPct, greetingNow } from "@/lib/format";
import { OsLoading, OsEmpty, OsError } from "@/components/os/States";

type Feed = {
  greeting_date: string;
  restaurant_name: string;
  period: string;
  revenue: { revenue: number; orders: number; avg_order: number; pace_projection: number };
  orders: { revenue: number; orders: number; delayed: number; active_now: number; split: Record<string, number> };
  kitchen: { avg_prep_min: number; delay_risk: number; bottleneck: string | null };
  stock: { low_stock: { name: string; qty: number }[]; expiring_48h: string[]; waste_pct_week: number };
  bookings: { covers_today: number; next_reservation_min: number | null; waitlist: number; no_show_pct: number };
  staff: { scheduled: number; on_shift: number; overtime_risk: number; labor_cost_pct: number };
  attention: { id: string; domain: string; title: string; why: string; what_to_do: string; impact: string; status: string }[];
  pulse: { domain: string; headline: string; detail: string }[];
  performance: { revenue_trend: { date: string; revenue: number; orders: number }[] };
};

const PERIODS = ["1h", "today", "7d", "30d"] as const;
const PERIOD_LABEL: Record<string, string> = { "1h": "1H", today: "Today", "7d": "7D", "30d": "30D" };

export default function OsHomePage() {
  const router = useRouter();
  const [feed, setFeed] = useState<Feed | null>(null);
  const [err, setErr] = useState(false);
  const [period, setPeriod] = useState("today");
  const [firstName, setFirstName] = useState("");

  const load = useCallback((p: string) => {
    setErr(false);
    api.get<Feed>(`/api/v1/overview/today?period=${p}`)
      .then((r) => setFeed(r.data))
      .catch(() => setErr(true));
  }, []);

  useEffect(() => { load(period); }, [period, load]);
  useEffect(() => {
    // First name for the greeting — from the session/me endpoint if available.
    api.get("/api/v1/auth/me").then((r) => {
      const name: string = r.data?.name || r.data?.full_name || "";
      setFirstName(name.split(" ")[0] || "");
    }).catch(() => {});
  }, []);

  const decide = async (cardId: string, decision: "approved" | "later" | "rejected") => {
    await api.post(`/api/v1/overview/attention/${encodeURIComponent(cardId)}/decision`, { decision });
    setFeed((f) => f && { ...f, attention: f.attention.filter((c) => c.id !== cardId) });
  };

  const askAi = (title: string) =>
    router.push(`/dashboard/os/chat?q=${encodeURIComponent(title)}`);

  return (
    <div className="space-y-6">
      {/* Greeting hero */}
      <section>
        <h1 className="text-2xl md:text-3xl font-semibold">
          {greetingNow()}{firstName ? `, ${firstName}` : ""}.
        </h1>
        <p className="text-sm text-[var(--muted-foreground)] mt-1">
          {feed ? <>Here&apos;s what deserves your attention at <b>{feed.restaurant_name}</b>.</> : "Loading your restaurant…"}
        </p>
      </section>

      {/* Period toggle */}
      <div className="inline-flex rounded-full border border-[var(--border)] overflow-hidden">
        {PERIODS.map((p) => (
          <button key={p} onClick={() => setPeriod(p)}
            className={`px-4 py-1.5 text-sm ${period === p ? "bg-[var(--accent)] text-white" : "text-[var(--muted-foreground)]"}`}>
            {PERIOD_LABEL[p]}
          </button>
        ))}
      </div>
      <p className="text-xs text-[var(--muted-foreground)] -mt-4">Prototype data · live POS sync coming soon</p>

      {err && <OsError message="Couldn't reach the kitchen right now." onRetry={() => load(period)} />}
      {!err && !feed && <OsLoading />}
      {!err && feed && (
        <>
          {/* 6 KPI cards */}
          <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            <Card label="Revenue" headline={fmtKes(feed.revenue.revenue)} verdict="Revenue so far"
              substats={[
                feed.revenue.orders ? `Average order · ${fmtKes(feed.revenue.avg_order)}` : "No orders in this period yet",
                feed.revenue.pace_projection ? `On pace for ~${fmtKes(feed.revenue.pace_projection)} today` : "",
              ].filter(Boolean)} />
            <Card label="Orders" headline={`${feed.orders.orders} orders`} verdict="Orders today"
              substats={[
                `${feed.orders.active_now} active now`,
                Object.entries(feed.orders.split).filter(([, v]) => v > 0).map(([k, v]) => `${v} ${k.replace("_", "-")}`).join(" · ") || "—",
              ]} />
            <Card label="Kitchen" headline={feed.kitchen.avg_prep_min ? `${feed.kitchen.avg_prep_min} min prep` : "On pace"} verdict="Kitchen"
              substats={[feed.kitchen.bottleneck ? `Bottleneck: ${feed.kitchen.bottleneck}` : "No delays reported"]} />
            <Card label="Stock" headline={feed.stock.low_stock.length ? `${feed.stock.low_stock.length} items to watch` : "Stock looks healthy"} verdict="Stock"
              substats={[
                feed.stock.low_stock[0] ? `${feed.stock.low_stock[0].name} projected to run out` : "Nothing below reorder point",
              ]} />
            <Card label="Bookings" headline={`${feed.bookings.covers_today} covers`} verdict="Covers expected"
              substats={[feed.bookings.next_reservation_min ? `Next reservation in ${feed.bookings.next_reservation_min} min` : "No upcoming reservation times yet"]} />
            <Card label="Staff" headline={`${feed.staff.scheduled} scheduled`} verdict="Coverage"
              substats={[
                `${feed.staff.on_shift} on shift now`,
                feed.staff.labor_cost_pct ? `Labor cost · ${fmtPct(feed.staff.labor_cost_pct)}` : "",
              ].filter(Boolean)} />
          </section>

          {/* What needs your attention */}
          <section>
            <h2 className="text-lg font-semibold">What needs your attention</h2>
            <p className="text-xs text-[var(--muted-foreground)]">The few things most worth knowing and acting on right now.</p>
            <div className="mt-3 space-y-3">
              {feed.attention.length === 0 && (
                <OsEmpty message="Nothing needs you right now. Enjoy the calm." hint="We'll flag anything urgent here the moment it appears." />
              )}
              {feed.attention.map((c) => (
                <div key={c.id} className="rounded-2xl border border-[var(--border)] p-4">
                  <p className="text-xs text-[var(--muted-foreground)]">{c.domain}</p>
                  <h3 className="font-medium mt-1">{c.title}</h3>
                  <p className="text-sm mt-2"><span className="text-[var(--muted-foreground)]">Why · </span>{c.why}</p>
                  <p className="text-sm mt-1"><span className="text-[var(--muted-foreground)]">What to do · </span>{c.what_to_do}</p>
                  {c.impact && <p className="text-xs text-emerald-600 mt-1">{c.impact}</p>}
                  <div className="flex gap-2 mt-3 flex-wrap">
                    <button onClick={() => decide(c.id, "approved")} className="rounded-full px-3 py-1.5 text-sm bg-[var(--accent)] text-white">Approve</button>
                    <button onClick={() => decide(c.id, "later")} className="rounded-full px-3 py-1.5 text-sm border border-[var(--border)]">Later</button>
                    <button onClick={() => decide(c.id, "rejected")} className="rounded-full px-3 py-1.5 text-sm border border-[var(--border)]">Reject</button>
                    <button onClick={() => askAi(router, c.title)} className="rounded-full px-3 py-1.5 text-sm border border-[var(--border)] text-[var(--accent)]">Ask AI about this</button>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* Operational pulse */}
          {feed.pulse.length > 0 && (
            <section>
              <h2 className="text-lg font-semibold">What&apos;s happening right now?</h2>
              <p className="text-sm text-[var(--muted-foreground)]">Operational pulse · refreshed just now</p>
              <div className="mt-3 divide-y divide-[var(--border)] rounded-2xl border border-[var(--border)]">
                {feed.pulse.map((p) => (
                  <div key={p.domain + p.headline} className="flex items-center justify-between px-4 py-3">
                    <span className="text-sm font-medium w-24">{p.domain}</span>
                    <span className="text-sm flex-1">{p.headline}</span>
                    <span className="text-xs text-[var(--muted-foreground)]">{p.detail}</span>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Business performance */}
          <section>
            <h2 className="text-lg font-semibold">Business performance</h2>
            <p className="text-sm text-[var(--muted-foreground)]">Last 7 days · enough context to know if the business is okay.</p>
            <div className="mt-3 rounded-2xl border border-[var(--border)] p-4 space-y-1">
              {feed.performance.revenue_trend.map((d) => (
                <div key={d.date} className="flex justify-between text-sm">
                  <span className="text-[var(--muted-foreground)]">{d.date}</span>
                  <span>{fmtKes(d.revenue)} · {d.orders} orders</span>
                </div>
              ))}
            </div>
          </section>
        </>
      )}
    </div>
  );
}

function askAi(router: ReturnType<typeof useRouter>, title: string) {
  router.push(`/dashboard/os/chat?q=${encodeURIComponent(title)}`);
}

function Card({ label, headline, verdict, substats }: {
  label: string; headline: string; verdict: string; substats: string[];
}) {
  return (
    <div className="rounded-2xl border border-[var(--border)] p-5">
      <p className="text-xs uppercase tracking-wide text-[var(--muted-foreground)]">{label}</p>
      <p className="text-2xl font-semibold mt-2">{headline}</p>
      <p className="text-sm mt-1">{verdict}</p>
      {substats.map((s, i) => (
        <p key={i} className="text-xs text-[var(--muted-foreground)] mt-1">{s}</p>
      ))}
    </div>
  );
}