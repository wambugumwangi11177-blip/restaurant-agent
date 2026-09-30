"use client";
import { useState } from "react";
import api from "@/lib/api";
import { withRetry } from "@/lib/retry";
import { fmtKes } from "@/lib/format";
type Result = {
  before: number;
  after: number;
  delta: number;
  price: number;
  units: number;
  notice: string;
};
export default function DemoSimulation() {
  const [price, setPrice] = useState(5),
    [demand, setDemand] = useState(0);
  const [result, setResult] = useState<Result | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(false);
  async function run() {
    setBusy(true);
    setError(false);
    try {
      const r = await withRetry(
        () => api.post<Result>("/api/v1/demo/simulate", { price_change_pct: price, demand_change_pct: demand }),
        { tries: 3 },
      );
      setResult(r.data);
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-5">
      <h2 className="font-display text-2xl">Try it before you change it</h2>
      <p className="mt-2 text-sm">
        Beef pilau · compare daily contribution after food cost.
      </p>
      <div className="my-5 grid gap-5 sm:grid-cols-2">
        <label className="text-sm">
          Price change: {price}%
          <input
            className="mt-3 block w-full"
            type="range"
            min={-30}
            max={30}
            value={price}
            onChange={(e) => {
              setPrice(Number(e.target.value));
              setResult(null);
            }}
          />
        </label>
        <label className="text-sm">
          Assumed demand change: {demand}%
          <input
            className="mt-3 block w-full"
            type="range"
            min={-50}
            max={50}
            value={demand}
            onChange={(e) => {
              setDemand(Number(e.target.value));
              setResult(null);
            }}
          />
        </label>
      </div>
      <button
        disabled={busy}
        onClick={run}
        className="rounded-lg bg-[var(--v-primary)] px-4 py-3 text-sm text-[var(--v-primary-foreground)]"
      >
        {busy ? "Calculating…" : "Calculate scenario"}
      </button>
      {error && (
        <p role="alert" className="mt-3">
          Could not calculate. Please try again.
        </p>
      )}
      {result && (
        <div aria-live="polite" className="mt-5 space-y-2">
          <p className="font-display text-2xl">
            {fmtKes(result.before)} → {fmtKes(result.after)}
          </p>
          <p>Contribution change: {fmtKes(result.delta)} / day</p>
          <p className="text-sm">
            {result.units} portions at {fmtKes(result.price)} each
          </p>
          <p className="text-xs text-[var(--v-muted-foreground)]">
            {result.notice}
          </p>
        </div>
      )}
    </section>
  );
}
