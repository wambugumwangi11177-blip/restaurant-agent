"use client";
// Vibanda OS — copy of the sketch's /ai page, wired to the real backend.
// Anatomy from the sketch: hero (badge "Your operating partner" + "Ask AI."),
// prototype-data badge, ask bar, searchable question groups, transcript
// ("You asked" → Finding / Why this matters / Estimated impact / Recommended
// next step card), "This period" aside with REAL numbers from /overview/today.
// POST /api/v1/ai/chat, with GET /api/v1/ai/ask as the deterministic fallback.
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Search, Send, Sparkles, ShieldCheck, Info, ChevronRight } from "lucide-react";
import api from "@/lib/api";
import { fmtKes } from "@/lib/format";
import { QUESTION_GROUPS } from "@/lib/osSuggestions";
import { OsLoading, OsError } from "@/components/os/States";

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

function OsChatInner() {
  const params = useSearchParams();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [filter, setFilter] = useState("");
  const [busy, setBusy] = useState(false);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [overviewError, setOverviewError] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let active = true;
    api.get<Overview>("/api/v1/overview/today")
      .then((r) => { if (active) setOverview(r.data); })
      .catch(() => { if (active) setOverviewError(true); });
    return () => { active = false; };
  }, []);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [turns]);

  const ask = async (question: string) => {
    const q = question.trim();
    if (!q || busy) return;
    setInput("");
    setTurns((t) => [...t, { question: q, answer: null }]);
    setBusy(true);
    try {
      // One grounded question path; an API failure is never replaced with
      // unrelated strategy advice or a cached snapshot from another period.
      let card: AskCard | null = null;
      let llmReply: string | undefined;
      try {
        const r = await api.post("/api/v1/ai/chat", {
          question: q,
          history: turns.slice(-3).flatMap((t) => [
            { role: "user", content: t.question },
            ...(t.answer ? [{ role: "assistant", content: (t.answer.llmReply || t.answer.finding).slice(0, 4000) }] : []),
          ]),
        });
        card = r.data?.grounded ?? null;
        llmReply = r.data?.llm_reply ?? undefined;
      } catch {
        const r = await api.get<AskCard>("/api/v1/ai/ask", { params: { question: q } });
        card = r.data;
      }
      if (!card?.finding) throw new Error("No verified answer returned");

      const answer: Answer = {
            finding: card.finding,
            why: card.why,
            impact: card.impact || "—",
            action: card.recommendation,
            module: card.module,
            llmReply,
            aiSteps: (card.steps || []).map((s) => ({ action: s.action ?? "", why: s.why })),
          };
      setTurns((t) => t.map((turn, i) => (i === t.length - 1 ? { question: q, answer } : turn)));
    } catch {
      setTurns((t) => t.map((turn, i) => (i === t.length - 1 ? { question: q, answer: null, error: true } : turn)));
    } finally {
      setBusy(false);
    }
  };

  // Prefill from attention cards (?q=)
  useEffect(() => {
    const q = params.get("q");
    if (q) ask(q);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
          Prototype data · Macsoft is not connected
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
          maxLength={500}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask anything about your restaurant..."
          className="min-w-0 flex-1 bg-transparent px-3 py-4 text-sm outline-none placeholder:text-[hsl(207_12%_46_/_0.7)]"
        />
        <button type="submit" disabled={busy || input.trim().length < 3} aria-label="Send question"
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
                <div key={i} className="space-y-3">
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
                  {t.error && <OsError message="Couldn't verify an answer. Please retry." onRetry={() => ask(t.question)} />}
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
              <div ref={endRef} />
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
            {!overview ? (
              <p role={overviewError ? "alert" : "status"} className="text-sm text-[var(--v-muted-foreground)]">
                {overviewError ? "Today's figures are unavailable. Reload to retry." : "Loading today's figures…"}
              </p>
            ) : <div className="space-y-4">
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
            </div>}
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
