"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import OwnerShell from "@/components/eleven/OwnerShell";
import api from "@/lib/api";

export default function TeamRulesPage() {
  const [alerts, setAlerts] = useState(true);
  const [maxHours, setMaxHours] = useState(52);
  const [maxDays, setMaxDays] = useState(6);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .get("/api/v1/team/rules")
      .then((r) => {
        setAlerts(r.data.alerts_enabled);
        setMaxHours(r.data.max_hours_per_week);
        setMaxDays(r.data.max_consecutive_days);
      })
      .catch(() => setError("Rules could not be loaded."));
  }, []);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    try {
      await api.put("/api/v1/team/rules", {
        alerts_enabled: alerts,
        max_hours_per_week: maxHours,
        max_consecutive_days: maxDays,
      });
      setMessage("Team rules saved. Alerts run when the schedule changes.");
    } catch {
      setError("Rules were not saved.");
    }
  }

  return (
    <OwnerShell title="Team rules">
      <p className="mb-4 text-sm text-zinc-400">
        Checked against your staff contracts. Manager changes that break these rules need your approval.
      </p>
      <form onSubmit={save} className="owner-glass-panel owner-premium-stack p-5">
        <label className="flex items-center gap-3 text-sm text-[var(--text)]">
          <input type="checkbox" checked={alerts} onChange={(e) => setAlerts(e.target.checked)} />
          Labour alerts on
        </label>
        <label className="block text-sm">
          Max hours per week
          <input
            type="number"
            min={1}
            max={168}
            className="leviii-input mt-1 w-full rounded-2xl px-3 py-2"
            value={maxHours}
            onChange={(e) => setMaxHours(Number(e.target.value))}
          />
        </label>
        <label className="block text-sm">
          Max days in a row (one rest day in 7 → default 6)
          <input
            type="number"
            min={1}
            max={7}
            className="leviii-input mt-1 w-full rounded-2xl px-3 py-2"
            value={maxDays}
            onChange={(e) => setMaxDays(Number(e.target.value))}
          />
        </label>
        {error && <p className="text-sm text-red-300">{error}</p>}
        {message && <p className="text-sm text-[var(--text)]">{message}</p>}
        <button type="submit" className="leviii-btn-primary w-full py-2">
          Save rules
        </button>
      </form>
      <Link href="/eleven/team" className="mt-4 inline-block text-sm text-[var(--accent)] underline">
        Back to Team
      </Link>
    </OwnerShell>
  );
}