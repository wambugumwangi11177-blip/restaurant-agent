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
  const [sendErr, setSendErr] = useState(false);
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    setErr(false);
    api.get("/api/v1/support/tickets")
      .then((r) => setTickets(r.data))
      .catch(() => setErr(true));
  }, []);
  useEffect(() => { load(); }, [load]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!subject.trim() || !message.trim()) return;
    setBusy(true);
    setSendErr(false);
    setSent(false);
    try {
      await api.post("/api/v1/support/tickets", { subject: subject.trim(), message: message.trim() });
      setSubject(""); setMessage(""); setSent(true);
      load();
      setTimeout(() => setSent(false), 4000);
    } catch { setSendErr(true); }
    finally { setBusy(false); }
  }

  return (
    <div className="max-w-4xl space-y-6">
      <section>
        <h1 className="font-display text-[clamp(2rem,4vw,3.25rem)] font-semibold leading-[1.02] tracking-[-0.045em]">Support<span className="text-[var(--v-primary)]">.</span></h1>
        <p className="text-sm text-[var(--v-muted-foreground)] mt-1">
          Tell us the moment something breaks — we&apos;re listening.
        </p>
      </section>

      <form onSubmit={submit} className="rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-5 space-y-3">
        <input
          aria-label="Issue subject"
          required
          maxLength={200}
          value={subject}
          onChange={(e) => setSubject(e.target.value)}
          placeholder="What happened? (one line)"
          className="w-full rounded-lg border border-[var(--v-border)] bg-transparent px-4 py-3 text-sm outline-none focus:border-[hsl(201_47%_29_/.65)]"
        />
        <textarea
          aria-label="Issue details"
          required
          maxLength={4000}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Describe the issue — what you saw, and where."
          rows={4}
          className="w-full rounded-lg border border-[var(--v-border)] bg-transparent px-4 py-3 text-sm outline-none focus:border-[hsl(201_47%_29_/.65)]"
        />
        <button type="submit" disabled={busy || !subject.trim() || !message.trim()}
          className="min-h-10 rounded-lg bg-[var(--v-primary)] px-4 py-2.5 text-[11px] font-bold text-[var(--v-primary-foreground)] hover:brightness-105 disabled:opacity-50">
          {busy ? "Sending…" : "Send to support"}
        </button>
        {sent && <p role="status" className="text-sm text-[var(--v-good)]">Your message was recorded. Track its status below.</p>}
        {sendErr && <p role="alert" className="text-sm text-red-600">Couldn't send your message. Your text is preserved; please try again.</p>}
      </form>

      <section>
        <p className="mb-1 text-[10px] font-bold uppercase tracking-[0.16em] text-[var(--v-muted-foreground)]">History</p>
        <h2 className="font-display text-2xl font-semibold tracking-[-0.035em]">Your past messages</h2>
        {err && <OsError message="Couldn't load your tickets." onRetry={load} />}
        {!err && tickets === null && <OsLoading rows={2} />}
        {!err && tickets && tickets.length === 0 && (
          <OsEmpty message="No issues reported yet." hint="When something goes wrong, this is where it shows up." />
        )}
        {tickets && tickets.length > 0 && (
          <div className="mt-3 divide-y divide-[var(--v-border)] rounded-xl border border-[var(--v-border)] bg-[var(--v-card)]">
            {tickets.map((t) => (
              <div key={t.id} className="flex items-center justify-between px-4 py-3">
                <span className="text-sm">{t.subject}</span>
                <span className="text-xs rounded-full px-2 py-0.5 border border-[var(--v-border)] text-[var(--v-muted-foreground)]">{t.status}</span>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
