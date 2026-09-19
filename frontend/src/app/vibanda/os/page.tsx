"use client";
// Vibanda OS — copy of the sketch's /ai page, wired to the real backend.
// Anatomy from the sketch: hero (badge "Your operating partner" + "Ask AI."),
// prototype-data badge, ask bar, searchable question groups, transcript
// ("You asked" → Finding / Why this matters / Estimated impact / Recommended
// next step card), "This period" aside with REAL numbers from /overview/today.
// Backend wiring (tracer): POST /api/v1/ai/strategy (goal→grounded plan,
// deterministic fallback when no LLM key).
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Search, Send, Sparkles, ShieldCheck, Info, ChevronRight } from "lucide-react";
import api from "@/lib/api";
import { fmtKes } from "@/lib/format";
import { QUESTION_GROUPS } from "@/lib/osSuggestions";
import { OsLoading } from "@/components/os/States";

type AiStep = { action: string; why?: string; expected_impact?: string };
type AskCard = {
  finding: string; why: string; impact: string; recommendation: string;
  module: string; steps: { action?: string; why?: string }[]; data?: Record<string, unknown>;
};

type Answer = {
  finding: string;
  why: string;
  impact: string;
  action: string;
  metric?: string;
  next?: string;
  module?: string;
  aiHeadline?: string;
  aiSteps?: AiStep[];
  llmReply?: string;
};

type Turn = { question: string; answer: Answer | null; error?: boolean };

type Overview = {
  restaurant_name: string;
  revenue: { revenue: number; orders: number; avg_order: number; pace_projection: number };
  orders: { orders: number; active_now: number };
  stock: { low_stock: { name: string }[] };
  bookings: { covers_today: number };
  staff: { scheduled: number };
};

// Map a free-text question to a grounded answer built from REAL overview data
// (deterministic — same contract as the backend's /ai/strategy fallback).
function groundingAnswer(q: string, ov: Overview | null): Answer {
  const s = q.toLowerCase();
  if (!ov) {
    return {
      finding: "I couldn't load today's numbers just now.",
      why: "The overview feed didn't respond — check your connection and try again.",
      impact: "—",
      action: "Retry the question in a moment.",
    };
  }
  if (s.includes("sales") || s.includes("revenue") || s.includes("money today")) {
    return {
      finding: `Revenue today is ${fmtKes(ov.revenue.revenue)} across ${ov.orders.orders} orders.`,
      why: "Counts every order recorded in your restaurant so far today (Nairobi calendar day).",
      impact: ov.revenue.pace_projection ? `On pace for ~${fmtKes(ov.revenue.pace_projection)} today` : "—",
      action: ov.revenue.pace_projection
        ? "Keep the current service rhythm; compare the pace against last week's same day in Business performance."
        : "Check back after the first orders of the day land.",
      metric: `Average order · ${fmtKes(ov.revenue.avg_order)}`,
    };
  }
  if (s.includes("run out") || s.includes("stock") || s.includes("waste") || s.includes("reorder") || s.includes("expire")) {
    const names = ov.stock.low_stock.map((i) => i.name);
    return {
      finding: names.length
        ? `${names.length} item${names.length === 1 ? "" : "s"} at or below reorder point: ${names.join(", ")}.`
        : "Nothing is below its reorder point right now.",
      why: names.length
        ? "Current quantity has reached the level where a normal delivery cycle may not arrive in time."
        : "Your stock levels are within their healthy ranges.",
      impact: names.length ? "Avoids emergency buying at higher prices" : "—",
      action: names.length ? `Raise today's order for ${names[0]} and confirm the next delivery slot.` : "No action needed today.",
    };
  }
  if (s.includes("book") || s.includes("customer") || s.includes("no-show") || s.includes("covers")) {
    return {
      finding: `${ov.bookings.covers_today} covers are expected today.`,
      why: "Counted from confirmed reservations on today's date.",
      impact: "—",
      action: ov.bookings.covers_today
        ? "Staff the floor for the peak windows you already know; keep a waitlist during them."
        : "Push a lunch offer to regulars to fill today's covers.",
    };
  }
  if (s.includes("staff") || s.includes("labor") || s.includes("shift") || s.includes("understaff")) {
    return {
      finding: `${ov.staff.scheduled} shifts are scheduled in the current period; ${ov.orders.active_now} orders are active right now.`,
      why: "Compare scheduled coverage against demand to spot over/understaffing.",
      impact: "—",
      action: "Match the shift plan to today's expected covers before the next service.",
    };
  }
  if (s.includes("focus") || s.includes("worried") || s.includes("health") || s.includes("one thing") || s.includes("everything")) {
    return ov.stock.low_stock.length
      ? {
          finding: `The most urgent thing today is stock: ${ov.stock.low_stock.map((i) => i.name).join(", ")} ${ov.stock.low_stock.length === 1 ? "is" : "are"} below reorder point.`,
          why: "A stockout forces emergency buying and can take items off the menu mid-service.",
          impact: "Protects today's menu availability",
          action: `Reorder ${ov.stock.low_stock[0].name} today.`,
          next: "Then review Business performance on Home for the 7-day trend.",
        }
      : {
          finding: `Nothing urgent — ${ov.orders.orders} orders and ${fmtKes(ov.revenue.revenue)} revenue so far today.`,
          why: "No items below reorder point and no stuck orders flagged.",
          impact: "—",
          action: "Use the quiet to review the 7-day performance trend on Home.",
        };
  }
  // Default: grounded overview snapshot
  return {
    finding: `Today: ${fmtKes(ov.revenue.revenue)} revenue · ${ov.orders.orders} orders · ${ov.bookings.covers_today} covers expected · ${ov.stock.low_stock.length} stock item(s) to watch.`,
    why: "Pulled live from your restaurant's data as of right now (Nairobi day).",
    impact: "—",
    action: ov.stock.low_stock.length
      ? `Most useful next step: reorder ${ov.stock.low_stock[0].name}.`
      : "Ask about sales, stock, bookings, staff, or the kitchen for specifics.",
  };
}

function OsChatInner() {
  const params = useSearchParams();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [filter, setFilter] = useState("");
  const [busy, setBusy] = useState(false);
  const [overview, setOverview] = useState<Overview | null>(null);
  // Settled (success OR failure) — not merely "loaded". A ?q= question must
  // wait for this, see the prefill effect below.
  const [overviewReady, setOverviewReady] = useState(false);
  const prefillAsked = useRef(false);
  const latestTurnRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.get<Overview>("/api/v1/overview/today")
      .then((r) => setOverview(r.data))
      .catch(() => {})
      .finally(() => setOverviewReady(true));
  }, []);

  // Bring the NEW question to the top of the viewport so the answer fills in
  // directly below it, in view.
  //
  // This used to scroll a marker placed AFTER the transcript to the top of the
  // viewport, which pushed the answer above the fold — the owner had to scroll
  // back up to read every reply. Keyed on turns.length, not `turns`, so the
  // page holds still while the answer streams into the card the reader is
  // already looking at.
  useEffect(() => {
    if (!turns.length) return;
    latestTurnRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [turns.length]);

  const ask = async (question: string) => {
    const q = question.trim();
    if (!q || busy) return;
    setInput("");
    setTurns((t) => [...t, { question: q, answer: null }]);
    setBusy(true);
    try {
      // Tracer wiring: real backend. /ai/strategy takes a goal + timeframe and
      // returns a grounded plan (LLM when GROQ_API_KEY is set, deterministic
      // otherwise). We also compute a deterministic grounded answer from the
      // overview feed so the card is always truthful even if the AI errors.
      // Real-time LLM chat: POST /ai/chat grounds the question in the RIGHT
      // ai/ module's real data, then OpenRouter writes the conversational
      // reply from those numbers. Strategy steps + deterministic card remain
      // as fallbacks so the chat never goes dark.
      let card: AskCard | null = null;
      let llmReply: string | undefined;
      let aiSteps: { action: string; why?: string; expected_impact?: string }[] = [];
      let aiHeadline = "";
      try {
        const r = await api.post("/api/v1/ai/chat", {
          question: q,
          history: turns.slice(-4).map((t) => ({ role: "user", content: t.question })),
        });
        card = r.data?.grounded ?? null;
        llmReply = r.data?.llm_reply ?? undefined;
      } catch { card = null; }
      try {
        const r2 = await api.post("/api/v1/ai/strategy", { goal: q, timeframe: "today" });
        const st = r2.data?.strategy;
        if (st?.steps?.length) {
          aiHeadline = st.headline ?? "";
          aiSteps = st.steps.slice(0, 5).map((s: { action?: string; why?: string; expected_impact?: string }) => ({
            action: s.action ?? "",
            why: s.why,
            expected_impact: s.expected_impact === "not quantified" ? undefined : s.expected_impact,
          }));
        }
      } catch { aiSteps = []; }

      const answer: Answer = card
        ? {
            finding: card.finding,
            why: card.why,
            impact: card.impact || "—",
            action: card.recommendation,
            module: card.module,
            llmReply,
            aiHeadline: aiHeadline || undefined,
            aiSteps: aiSteps.length ? aiSteps : (card.steps || []).map((s) => ({ action: s.action ?? "", why: s.why })),
          }
        : (() => {
            const g = groundingAnswer(q, overview);
            return { ...g, llmReply, aiSteps: aiSteps.length ? aiSteps : undefined, aiHeadline: aiSteps.length ? aiHeadline : undefined };
          })();
      setTurns((t) => t.map((turn, i) => (i === t.length - 1 ? { question: q, answer } : turn)));
    } finally {
      setBusy(false);
    }
  };

  // Prefill from Home's cards (?q=).
  //
  // Waits for the overview fetch to settle first. It used to fire on mount, in
  // parallel with that fetch, so `overview` was still null when the answer was
  // built — and every question arriving from Home got the "I couldn't load
  // today's numbers just now" fallback instead of a real answer. Home is the
  // main way into this page, so that was most questions.
  useEffect(() => {
    if (!overviewReady || prefillAsked.current) return;
    const q = params.get("q");
    if (!q) return;
    prefillAsked.current = true;
    ask(q);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [overviewReady]);

  const groups = useMemo(() => {
    const v = filter.trim().toLowerCase();
    return QUESTION_GROUPS.map((g) => ({
      ...g,
      questions: g.questions.filter((q) => q.toLowerCase().includes(v)),
    })).filter((g) => !v || g.name.toLowerCase().includes(v) || g.questions.length > 0);
  }, [filter]);

  return (
    <div className="animate-rise-in space-y-6">
      {/* Hero — sketch pattern */}
      <div className="mb-8 flex flex-col justify-between gap-5 sm:flex-row sm:items-end">
        <div>
          <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-[var(--v-border)] bg-[hsl(42_40%_99_/_0.65)] px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--v-muted-foreground)]">
            <span className="h-1.5 w-1.5 rounded-full bg-[var(--v-good)]" />
            Your operating partner
          </div>
          <h1 className="font-display text-[clamp(2rem,4vw,3.25rem)] font-semibold leading-[1.02] tracking-[-0.045em]">
            Ask AI<span className="text-[var(--v-primary)]">.</span>
          </h1>
          <p className="mt-3 text-sm text-[var(--v-muted-foreground)]">Ask anything about your restaurant.</p>
        </div>
        <div className="flex items-center gap-2 rounded-lg border border-[var(--v-border)] bg-[hsl(42_40%_99_/_0.55)] px-3 py-2 text-[10px] text-[var(--v-muted-foreground)]">
          <span className="flex h-4 w-4 items-center justify-center rounded-full bg-[var(--v-accent)] text-[var(--v-accent-foreground)]">
            <Info size={10} />
          </span>
          Prototype data · {overview?.restaurant_name ?? "Vibanda Village"}
        </div>
      </div>

      {/* Ask bar — sketch: floating card with glow on focus */}
      <form
        onSubmit={(e) => { e.preventDefault(); ask(input); }}
        className="sticky bottom-24 z-10 flex items-center rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] shadow-[0_12px_40px_hsl(201_47%_29_/.07)] transition-all focus-within:border-[hsl(201_47%_29_/.65)] focus-within:shadow-[0_12px_40px_hsl(43_76%_57_/.12)] md:bottom-4"
      >
        <Search size={17} className="ml-4 shrink-0 text-[var(--v-muted-foreground)]" />
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask anything about your restaurant..."
          className="min-w-0 flex-1 bg-transparent px-3 py-4 text-sm outline-none placeholder:text-[hsl(207_12%_46_/_0.7)]"
        />
        <button type="submit" disabled={busy}
          className="mr-2 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[var(--v-primary)] text-[var(--v-primary-foreground)] disabled:opacity-50">
          <Send size={15} />
        </button>
      </form>

      <div className="grid items-start gap-10 xl:grid-cols-[minmax(0,1fr)_285px]">
        <div>
          {/* Search filter — sketch pattern */}
          <div className="mb-4 flex items-center rounded-lg border border-[var(--v-border)] bg-[var(--v-card)] px-3 py-2">
            <Search size={14} className="text-[var(--v-muted-foreground)]" />
            <input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Search questions — try “profit”, “stock”, “staff”…"
              className="ml-2 w-full bg-transparent py-1 text-[13px] outline-none placeholder:text-[hsl(207_12%_46_/_0.7)]"
            />
          </div>

          {/* Transcript — sketch: "You asked" card + Finding answer card */}
          {turns.length > 0 && (
            <div className="mb-8 space-y-4">
              {turns.map((t, i) => (
                <div
                  key={i}
                  ref={i === turns.length - 1 ? latestTurnRef : undefined}
                  className="scroll-mt-4 space-y-3"
                >
                  {/* You asked */}
                  <div className="rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-4">
                    <div className="flex items-start gap-3">
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[var(--v-primary)] text-[var(--v-primary-foreground)]">
                        <Sparkles size={14} />
                      </div>
                      <p className="pt-1.5 text-[13px] font-semibold">{t.question}</p>
                    </div>
                  </div>
                  {/* Answer card */}
                  {t.answer && (
                    <div className="ml-11 overflow-hidden rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] shadow-[0_10px_35px_hsl(201_47%_29_/.05)]">
                      <div className="border-b border-[var(--v-border)] bg-[hsl(39_26%_93_/_0.45)] px-4 py-3">
                        <p className="text-[11px] font-medium text-[var(--v-muted-foreground)]">You asked · answered from {t.answer.module ? `the ${t.answer.module} module` : "your data"}</p>
                        <p className="mt-1 text-[13px] font-semibold">{t.question}</p>
                      </div>
                      <div className="space-y-5 p-4 sm:p-5">
                        {t.answer.llmReply && (
                          <div className="rounded-xl bg-[hsl(42_71%_75_/_0.18)] p-3.5">
                            <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-[hsl(208_29%_19_/_0.92)]">{t.answer.llmReply}</p>
                          </div>
                        )}
                        <div>
                          <p className="mb-1.5 text-[10px] font-bold uppercase tracking-[0.15em] text-[var(--v-primary)]">Finding</p>
                          <p className="text-[13px] leading-relaxed text-[hsl(208_29%_19_/_0.86)]">{t.answer.finding}</p>
                        </div>
                        <div>
                          <p className="mb-1.5 text-[10px] font-bold uppercase tracking-[0.15em] text-[var(--v-muted-foreground)]">Why this matters</p>
                          <p className="text-[13px] leading-relaxed text-[hsl(208_29%_19_/_0.72)]">{t.answer.why}</p>
                        </div>
                        <div className="flex flex-wrap gap-3 border-y border-[var(--v-border)] py-4">
                          <div className="min-w-[170px] flex-1">
                            <p className="text-[10px] font-bold uppercase tracking-[0.15em] text-[var(--v-muted-foreground)]">Estimated impact</p>
                            <p className="font-display mt-1.5 text-lg font-semibold text-[var(--v-primary)]">{t.answer.impact}</p>
                          </div>
                          {t.answer.metric && (
                            <div className="min-w-[150px] flex-1">
                              <p className="text-[10px] font-bold uppercase tracking-[0.15em] text-[var(--v-muted-foreground)]">Key metric</p>
                              <p className="font-display mt-1.5 text-lg font-semibold">{t.answer.metric}</p>
                            </div>
                          )}
                        </div>
                        <div className="rounded-xl border border-[var(--v-border)] bg-[hsl(39_26%_93_/_0.45)] p-4">
                          <p className="mb-2 text-[10px] font-bold uppercase tracking-[0.15em] text-[var(--v-primary)]">The recommendation</p>
                          <p className="text-sm leading-relaxed">{t.answer.action}</p>
                        </div>
                        {t.answer.aiSteps && t.answer.aiSteps.length > 0 && (
                          <div>
                            <p className="mb-2 text-[10px] font-bold uppercase tracking-[0.15em] text-[var(--v-primary)]">
                              {t.answer.aiHeadline || "Recommended next steps"}
                            </p>
                            <div className="space-y-2">
                              {t.answer.aiSteps.map((s, si) => (
                                <div key={si} className="rounded-lg border border-[var(--v-border)] p-3">
                                  <div className="flex items-start justify-between gap-2">
                                    <p className="text-[13px] font-semibold">{si + 1}. {s.action}</p>
                                    {s.expected_impact && (
                                      <span className="shrink-0 rounded-md bg-[hsl(42_71%_75_/_0.35)] px-1.5 py-0.5 text-[9px] font-bold text-[var(--v-primary)]">
                                        {s.expected_impact}
                                      </span>
                                    )}
                                  </div>
                                  {s.why && (
                                    <p className="mt-1 text-[11px] leading-relaxed text-[hsl(208_29%_19_/_0.62)]">{s.why}</p>
                                  )}
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                        {t.answer.next && (
                          <div>
                            <p className="mb-2 text-[10px] font-bold uppercase tracking-[0.15em] text-[var(--v-muted-foreground)]">Next step</p>
                            <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-[hsl(208_29%_19_/_0.82)]">{t.answer.next}</p>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                  {busy && i === turns.length - 1 && !t.answer && <OsLoading rows={1} />}
                </div>
              ))}
            </div>
          )}

          {/* Question groups — sketch zE component pattern */}
          <div className="space-y-5">
            {groups.length === 0 && (
              <div className="rounded-xl border border-dashed border-[var(--v-border)] px-5 py-10 text-center">
                <p className="mt-3 text-sm font-semibold">No matching questions</p>
                <p className="mt-1 text-xs text-[var(--v-muted-foreground)]">Try “profit”, “stock”, or “customers”, or ask in your own words above.</p>
              </div>
            )}
            {groups.map((g) => (
              <section key={g.name}>
                <div className="mb-2.5 flex items-center gap-2.5">
                  <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-[var(--v-muted)] text-[var(--v-primary)]">
                    <Sparkles size={14} />
                  </div>
                  <h2 className="text-[11px] font-bold uppercase tracking-[0.14em] text-[var(--v-muted-foreground)]">{g.name}</h2>
                </div>
                <div className="space-y-1">
                  {g.questions.slice(0, 4).map((q) => (
                    <button key={q} type="button" onClick={() => ask(q)}
                      className="group flex w-full items-center justify-between gap-3 rounded-lg border border-transparent px-2.5 py-2 text-left text-[12px] leading-snug text-[hsl(208_29%_19_/_0.82)] transition-all hover:border-[var(--v-border)] hover:bg-[var(--v-card)] hover:text-[var(--v-primary)]">
                      <span>{q}</span>
                      <ChevronRight size={14} className="shrink-0 text-[var(--v-muted-foreground)] opacity-45 transition-transform group-hover:translate-x-0.5 group-hover:text-[var(--v-primary)]" />
                    </button>
                  ))}
                </div>
              </section>
            ))}
          </div>
        </div>

        {/* "This period" aside — sketch layout, REAL numbers from /overview/today */}
        <aside className="hidden space-y-4 xl:block">
          <div className="rounded-xl border border-[var(--v-border)] bg-[hsl(42_40%_99_/_0.6)] p-4">
            <div className="mb-3 flex items-center justify-between">
              <p className="text-[10px] font-bold uppercase tracking-[0.15em] text-[var(--v-muted-foreground)]">This period</p>
            </div>
            <div className="space-y-4">
              <div>
                <p className="text-[10px] text-[var(--v-muted-foreground)]">Revenue</p>
                <p className="font-display mt-1 text-xl font-semibold">{fmtKes(overview?.revenue.revenue ?? 0)}</p>
                <div className="mt-1 flex items-center gap-1 text-[10px] font-medium text-[var(--v-good)]">
                  <ChevronRight size={11} /> {overview?.orders.orders ?? 0} orders today
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3 border-t border-[var(--v-border)] pt-3">
                <div>
                  <p className="text-[10px] text-[var(--v-muted-foreground)]">Covers today</p>
                  <p className="mt-1 text-sm font-semibold">{overview?.bookings.covers_today ?? 0}</p>
                </div>
                <div>
                  <p className="text-[10px] text-[var(--v-muted-foreground)]">Avg order</p>
                  <p className="mt-1 text-sm font-semibold">{fmtKes(overview?.revenue.avg_order ?? 0)}</p>
                </div>
              </div>
            </div>
          </div>
          <div className="rounded-xl border border-[var(--v-border)] bg-[var(--v-primary)] p-4 text-[var(--v-primary-foreground)]">
            <div className="flex items-center gap-2">
              <Sparkles size={15} />
              <p className="text-[10px] font-bold uppercase tracking-[0.15em] opacity-75">How AI helps</p>
            </div>
            <p className="font-display mt-4 text-lg font-semibold leading-tight">
              Less reporting.<br />More knowing.
            </p>
            <p className="mt-3 text-[11px] leading-relaxed opacity-75">
              Ask practical questions in plain language. Your answers are grounded in the numbers already in Restaurant OS.
            </p>
          </div>
          <div className="flex items-start gap-2.5 px-1 pt-1 text-[10px] leading-relaxed text-[var(--v-muted-foreground)]">
            <ShieldCheck size={14} className="mt-0.5 shrink-0" />
            <span>Answers come from your restaurant&apos;s real data. Always confirm operational changes with your team.</span>
          </div>
        </aside>
      </div>
    </div>
  );
}

export default function VibandaOsPage() {
  return (
    <Suspense fallback={<div className="p-6 text-sm text-[var(--v-muted-foreground)]">Loading…</div>}>
      <OsChatInner />
    </Suspense>
  );
}