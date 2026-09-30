"use client";
import { useState } from "react";
import api from "@/lib/api";
export default function DemoCreative({
  topic = "intelligence",
  period,
}: {
  topic?: string;
  period?: string;
}) {
  const [text, setText] = useState(""),
    [label, setLabel] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(false);
  async function write() {
    setBusy(true);
    setError(false);
    try {
      const r = await api.post(
        "/api/v1/demo/chat",
        {
          question:
            "Give me a short creative take on this sample evidence and one idea worth testing.",
          topic,
          creative: true,
          report_period: period,
        },
        { timeout: 45000 },
      );
      setText(r.data.answer_text);
      setLabel(
        r.data.creative
          ? `AI-written · idea to test${r.data.cached ? " · cached" : ""}`
          : r.data.reason || "Calculated scenario explanation",
      );
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-display text-xl">A fresh perspective</h2>
        <button
          disabled={busy}
          onClick={write}
          className="rounded-lg border border-[var(--v-border)] px-3 py-2 text-xs font-semibold"
        >
          {busy
            ? "Writing…"
            : text
              ? "Read cached take"
              : "Write a creative take"}
        </button>
      </div>
      <p className="mt-2 text-xs text-[var(--v-muted-foreground)]">
        Optional creative layer · uses the sample evidence · cached for 30
        minutes.
      </p>
      {text && (
        <>
          <p className="mt-4 whitespace-pre-wrap text-sm leading-7">{text}</p>
          <p className="mt-3 text-xs text-[var(--v-muted-foreground)]">
            {label}
          </p>
        </>
      )}
      {error && (
        <p role="alert" className="mt-3 text-xs">
          Could not load a take. The calculated figures remain available.
        </p>
      )}
    </section>
  );
}
