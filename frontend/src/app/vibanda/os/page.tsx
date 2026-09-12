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
    <div className="max-w-3xl space-y-4">
      <section>
        <h1 className="text-2xl font-semibold">Ask anything about your restaurant</h1>
        <p className="text-sm text-[var(--muted-foreground)] mt-1">
          Every part of your restaurant is connected — money, kitchen, menu, stock, bookings, staff, purchasing.
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
                  className="rounded-full border border-[var(--border)] px-3 py-1.5 text-sm hover:border-[var(--accent)]">
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
            className={`rounded-2xl px-4 py-3 text-sm max-w-[85%] whitespace-pre-wrap ${
              t.role === "user"
                ? "bg-[var(--accent)] text-white ml-auto"
                : "border border-[var(--border)]"
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
        className="sticky bottom-24 md:bottom-4 flex gap-2"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask anything about your restaurant…"
          className="flex-1 rounded-full border border-[var(--border)] bg-[var(--card)] px-4 py-3 text-sm outline-none focus:border-[var(--accent)]"
        />
        <button type="submit" disabled={busy}
          className="rounded-full px-5 py-3 text-sm bg-[var(--accent)] text-white disabled:opacity-50">
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
