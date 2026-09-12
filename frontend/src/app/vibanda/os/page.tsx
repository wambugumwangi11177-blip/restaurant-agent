"use client";
// Restaurant OS — CHAT ("Ask anything about your restaurant").
// Tracer build: wire to existing POST /ai/strategy (goal -> grounded plan,
// deterministic fallback when no LLM). Suggestions per domain; ?q= prefill.
import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import api from "@/lib/api";
import { OsLoading, OsError } from "@/components/os/States";
import { SUGGESTIONS } from "@/lib/osSuggestions";

type Turn = { role: "user" | "assistant"; text: string };

function OsChatInner() {
  const params = useSearchParams();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const q = params.get("q");
    if (q) { setInput(q); ask(q); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [turns]);

  async function ask(question: string) {
    if (!question.trim() || busy) return;
    setTurns((t) => [...t, { role: "user", text: question }]);
    setInput("");
    setBusy(true); setErr(false);
    try {
      const r = await api.post("/api/v1/ai/strategy", { goal: question, timeframe: "today" });
      const data = r.data;
      const text = typeof data === "string" ? data
        : data?.plan ?? data?.answer ?? data?.narrative ?? JSON.stringify(data, null, 2);
      setTurns((t) => [...t, { role: "assistant", text: String(text) }]);
    } catch {
      setErr(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-4xl space-y-4">
      <section>
        <h1 className="font-display text-[clamp(2rem,4vw,3.25rem)] font-semibold leading-[1.02] tracking-[-0.045em]">Ask anything<span className="text-[var(--v-primary)]">.</span></h1>
        <p className="mt-3 text-sm text-[var(--v-muted-foreground)]">
          Ask anything about your restaurant — every part is connected: money, kitchen, menu, stock, bookings, staff, purchasing.
        </p>
      </section>

      {/* Suggested questions per domain */}
      {turns.length === 0 && (
        <div className="space-y-2">
          {Object.entries(SUGGESTIONS).map(([domain, qs]) => (
            <div key={domain} className="flex items-start gap-2 flex-wrap">
              <span className="text-xs font-medium w-20 pt-1.5 text-[var(--muted-foreground)]">{domain}</span>
              {qs.map((q) => (
                <button key={q} onClick={() => ask(q)}
                  className="rounded-lg border border-transparent px-2.5 py-2 text-left text-[12px] text-[hsl(208_29%_19_/_0.82)] transition-all hover:border-[var(--v-border)] hover:bg-[var(--v-card)] hover:text-[var(--v-primary)]">
                  {q}
                </button>
              ))}
            </div>
          ))}
        </div>
      )}

      {/* Conversation */}
      <div className="space-y-3">
        {turns.map((t, i) => (
          <div key={i}
            className={`rounded-xl px-4 py-3 text-[13px] max-w-[85%] whitespace-pre-wrap leading-relaxed ${
              t.role === "user"
                ? "bg-[var(--v-primary)] text-[var(--v-primary-foreground)] ml-auto"
                : "border border-[var(--v-border)] bg-[var(--v-card)]"
            }`}>
            {t.text}
          </div>
        ))}
        {busy && <OsLoading rows={1} />}
        {err && <OsError message="The AI chef is taking a break — try again in a moment." onRetry={() => setErr(false)} />}
        <div ref={endRef} />
      </div>

      {/* Composer */}
      <form
        onSubmit={(e) => { e.preventDefault(); ask(input); }}
        className="sticky bottom-24 md:bottom-4 flex items-center rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] shadow-[0_12px_40px_hsl(201_47%_29_/.07)] transition-all focus-within:border-[hsl(201_47%_29_/.65)]"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask anything about your restaurant…"
          className="min-w-0 flex-1 bg-transparent px-3 py-4 text-sm outline-none placeholder:text-[hsl(207_12%_46_/_0.7)]"
        />
        <button type="submit" disabled={busy}
          className="mr-2 rounded-lg bg-[var(--v-primary)] px-3.5 py-2.5 text-[11px] font-bold text-[var(--v-primary-foreground)] disabled:opacity-50">
          Ask
        </button>
      </form>
    </div>
  );
}

export default function OsChatPage() {
  return (
    <Suspense fallback={<div className="p-6 text-sm text-[var(--muted-foreground)]">Loading…</div>}>
      <OsChatInner />
    </Suspense>
  );
}
