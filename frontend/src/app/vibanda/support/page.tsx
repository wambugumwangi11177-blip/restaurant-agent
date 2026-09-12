"use client";
// Restaurant OS — SUPPORT. Direct line: report an issue the moment it happens
// (POST /support/tickets), plus thread of past tickets (GET /support/tickets).
import { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import { OsLoading, OsEmpty, OsError } from "@/components/os/States";

type Ticket = { id: number; subject: string; status: string; created_at?: string };

export default function OsSupportPage() {
  const [tickets, setTickets] = useState<Ticket[] | null>(null);
  const [err, setErr] = useState(false);
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.get("/api/v1/support/tickets")
      .then((r) => setTickets(r.data))
      .catch(() => setErr(true));
  }, []);
  useEffect(() => { load(); }, [load]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!subject.trim() || !message.trim()) return;
    setBusy(true);
    try {
      await api.post("/api/v1/support/tickets", { subject, message });
      setSubject(""); setMessage(""); setSent(true);
      load();
      setTimeout(() => setSent(false), 4000);
    } catch { setErr(true); }
    finally { setBusy(false); }
  }

  return (
    <div className="max-w-2xl space-y-6">
      <section>
        <h1 className="text-2xl font-semibold">Support</h1>
        <p className="text-sm text-[var(--muted-foreground)] mt-1">
          Tell us the moment something breaks — we&apos;re listening.
        </p>
      </section>

      <form onSubmit={submit} className="rounded-2xl border border-[var(--border)] p-5 space-y-3">
        <input
          value={subject}
          onChange={(e) => setSubject(e.target.value)}
          placeholder="What happened? (one line)"
          className="w-full rounded-xl border border-[var(--border)] bg-transparent px-4 py-3 text-sm outline-none focus:border-[var(--accent)]"
        />
        <textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Describe the issue — what you saw, and where."
          rows={4}
          className="w-full rounded-xl border border-[var(--border)] bg-transparent px-4 py-3 text-sm outline-none focus:border-[var(--accent)]"
        />
        <button type="submit" disabled={busy}
          className="rounded-full px-5 py-2.5 text-sm bg-[var(--accent)] text-white disabled:opacity-50">
          {busy ? "Sending…" : "Send to support"}
        </button>
        {sent && <p className="text-sm text-emerald-600">Received. Our team will get back to you shortly.</p>}
      </form>

      <section>
        <h2 className="text-lg font-semibold">Your past messages</h2>
        {err && <OsError message="Couldn't load your tickets." onRetry={load} />}
        {!err && tickets === null && <OsLoading rows={2} />}
        {!err && tickets && tickets.length === 0 && (
          <OsEmpty message="No issues reported yet." hint="When something goes wrong, this is where it shows up." />
        )}
        {tickets && tickets.length > 0 && (
          <div className="mt-3 divide-y divide-[var(--border)] rounded-2xl border border-[var(--border)]">
            {tickets.map((t) => (
              <div key={t.id} className="flex items-center justify-between px-4 py-3">
                <span className="text-sm">{t.subject}</span>
                <span className="text-xs rounded-full px-2 py-0.5 border border-[var(--border)] text-[var(--muted-foreground)]">{t.status}</span>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}