"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, fmtDate, usd } from "@/lib/api";
import { can, useMe } from "@/components/shell";
import { Badge, Button, Card, Empty, ErrorBox, PageHeader, Pre } from "@/components/ui";

type Ops = { llm_provider: string | null; llm_spend_today_usd: string; llm_daily_cap_usd: string; channels: Record<string, boolean>; pending_approvals: number; env: string };
type Note = { id: number; title: string; body: string; link: string | null; read: boolean; created_at: string };
type Ev = { id: number; type: string; entity_type: string | null; entity_id: number | null; payload: Record<string, unknown>; created_at: string };

export default function Home() {
  const me = useMe();
  const tz = me.workspace.timezone;
  const [status, setStatus] = useState<string | null>(null);
  const [ops, setOps] = useState<Ops | null>(null);
  const [notes, setNotes] = useState<Note[] | null>(null);
  const [events, setEvents] = useState<Ev[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [s, o, n, ev] = await Promise.all([
        can(me, "agents.run") ? api<{ output: string }>("agents/status/run", { body: {} }) : null,
        can(me, "ops.read") ? api<Ops>("ops/status") : null,
        api<Note[]>("notifications?unread_only=true"),
        can(me, "events.read") ? api<Ev[]>("events?limit=15") : [],
      ]);
      setStatus(s?.output ?? null);
      setOps(o);
      setNotes(n);
      setEvents(ev);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [me]);

  useEffect(() => {
    load();
  }, [load]);

  async function readAll() {
    await api("notifications/read-all", { method: "POST" });
    setNotes([]);
  }

  return (
    <>
      <PageHeader title={`Good day, ${me.user.full_name.split(" ")[0]}`} subtitle="What needs you right now, what the OS did, and what it cost." />
      <ErrorBox error={error} />
      <div className="grid gap-4 lg:grid-cols-2">
        {status && (
          <Card>
            <div className="mb-2 flex items-center justify-between">
              <h2 className="text-sm font-semibold">Status</h2>
              <Link href="/approvals" className="text-xs underline">Open approvals</Link>
            </div>
            <Pre>{status}</Pre>
          </Card>
        )}
        <Card>
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-sm font-semibold">Notifications</h2>
            {notes && notes.length > 0 && <Button variant="secondary" onClick={readAll}>Mark all read</Button>}
          </div>
          {notes === null ? <Empty>Loading…</Empty> : notes.length === 0 ? <Empty>Nothing unread.</Empty> : (
            <ul className="divide-y divide-zinc-100 text-sm dark:divide-zinc-800">
              {notes.map((n) => (
                <li key={n.id} className="py-2">
                  <div className="font-medium">{n.link ? <Link href={n.link} className="underline">{n.title}</Link> : n.title}</div>
                  <div className="text-zinc-500">{n.body}</div>
                  <div className="text-xs text-zinc-400">{fmtDate(n.created_at, tz)}</div>
                </li>
              ))}
            </ul>
          )}
        </Card>
        {ops && (
          <Card>
            <h2 className="mb-2 text-sm font-semibold">System</h2>
            <dl className="grid grid-cols-2 gap-y-1 text-sm">
              <dt className="text-zinc-500">LLM provider</dt><dd>{ops.llm_provider ?? <Badge tone="amber">none: deterministic mode</Badge>}</dd>
              <dt className="text-zinc-500">LLM spend today</dt><dd>{usd(ops.llm_spend_today_usd)} of {usd(ops.llm_daily_cap_usd)}</dd>
              <dt className="text-zinc-500">WhatsApp</dt><dd>{ops.channels.whatsapp ? <Badge tone="green">configured</Badge> : <Badge tone="amber">not configured</Badge>}</dd>
              <dt className="text-zinc-500">Email</dt><dd>{ops.channels.email ? <Badge tone="green">configured</Badge> : <Badge tone="amber">not configured</Badge>}</dd>
              <dt className="text-zinc-500">Environment</dt><dd>{ops.env}</dd>
            </dl>
          </Card>
        )}
        {events.length > 0 && (
          <Card>
            <h2 className="mb-2 text-sm font-semibold">Recent activity</h2>
            <ul className="space-y-1 text-sm">
              {events.map((e) => (
                <li key={e.id} className="flex justify-between gap-3">
                  <span><Badge>{e.type}</Badge> {e.entity_type && `${e.entity_type} #${e.entity_id}`}</span>
                  <span className="shrink-0 text-xs text-zinc-400">{fmtDate(e.created_at, tz)}</span>
                </li>
              ))}
            </ul>
          </Card>
        )}
      </div>
    </>
  );
}
