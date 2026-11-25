"use client";

import { useState } from "react";
import { Loader2, Send } from "lucide-react";
import api from "@/lib/api";
import OwnerShell from "@/components/eleven/OwnerShell";
import ExplainedCard from "@/components/eleven/charts/ExplainedCard";
import { formatKes } from "@/lib/formatKes";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

type ChatResponse = {
  answer_text?: string | null;
  llm_reply?: string | null;
  mini_chart?: { day: string; kes: number }[];
  freshness_line?: string;
  grounded?: { finding?: string; why?: string; recommendation?: string };
  data_availability?: string;
};

const STARTERS = [
  "How are sales today?",
  "Which stock moves happened this week?",
  "Which bills are waiting on me?",
];

function replyText(answer: ChatResponse): string {
  return (
    answer.answer_text ||
    answer.llm_reply ||
    [answer.grounded?.finding, answer.grounded?.why, answer.grounded?.recommendation].filter(Boolean).join(" ") ||
    "I could not answer that from your records."
  );
}

export default function ElevenAskPage() {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<ChatResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function ask(text: string) {
    const q = text.trim();
    if (q.length < 3) return;
    setError("");
    setLoading(true);
    setAnswer(null);
    try {
      const response = await api.post<ChatResponse>("/api/v1/ai/chat", {
        question: q,
        answer_mode: "analysis",
      });
      setAnswer(response.data);
    } catch {
      setError("That question could not be answered. Check your connection and try again.");
    } finally {
      setLoading(false);
    }
  }

  const text = answer ? replyText(answer) : "";
  const chart = answer?.mini_chart ?? [];
  const numeric = chart.length > 0;

  return (
    <OwnerShell title="Ask">
      <p className="mb-3 text-xs text-zinc-400">Answers use your till and store records. Nothing is invented when data is missing.</p>
      <form
        className="owner-glass-panel flex gap-2 rounded-2xl p-3"
        onSubmit={(e) => {
          e.preventDefault();
          void ask(question);
        }}
      >
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask about sales, stock, bills…"
          className="min-h-11 flex-1 rounded-full border border-white/15 bg-black/30 px-4 text-sm"
          disabled={loading}
        />
        <button
          type="submit"
          disabled={loading || question.trim().length < 3}
          className="flex h-11 w-11 items-center justify-center rounded-full bg-white text-black disabled:opacity-50"
          aria-label="Send"
        >
          {loading ? <Loader2 className="animate-spin" size={18} /> : <Send size={18} />}
        </button>
      </form>
      {error && <p className="mt-3 text-sm text-red-300">{error}</p>}
      {answer && (
        <ExplainedCard
          title="Answer"
          headline={text.slice(0, 120) + (text.length > 120 ? "…" : "")}
          what={answer.grounded?.why || "A direct read from your connected records."}
          freshness={answer.freshness_line || (answer.data_availability === "available" ? "Live · from your till" : "As entered")}
          hasData={!!text}
          emptyHint="Ask a specific question about sales, stock or bills."
        >
          <p className="text-sm leading-6 text-zinc-200">{text}</p>
          {numeric && (
            <ResponsiveContainer width="100%" height={72} className="mt-3">
              <BarChart data={chart}>
                <XAxis dataKey="day" hide />
                <YAxis hide />
                <Tooltip formatter={(v) => formatKes(Number(v))} />
                <Bar dataKey="kes" fill="#8b7d72" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </ExplainedCard>
      )}
      <h2 className="owner-label mt-6">Try asking</h2>
      <div className="mt-2 flex flex-wrap gap-2">
        {STARTERS.map((q) => (
          <button
            key={q}
            type="button"
            className="rounded-full border border-white/20 px-3 py-2 text-left text-xs hover:border-white/40"
            onClick={() => {
              setQuestion(q);
              void ask(q);
            }}
          >
            {q}
          </button>
        ))}
      </div>
    </OwnerShell>
  );
}