"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, fmtDate } from "@/lib/api";
import { can, useMe } from "@/components/shell";
import { Badge, Button, Card, Empty, ErrorBox, Input, Label, PageHeader, Pre, Select, statusTone, Textarea } from "@/components/ui";

type Proposal = {
  id: number; tool: string; summary: string; status: string; args: Record<string, unknown>; final_args: Record<string, unknown> | null;
  edited: boolean; auto_approved: boolean; agent_run_id: number | null; decision_reason: string | null; result: unknown; error: string | null;
  created_at: string; decided_at: string | null;
};
type Policy = { tool: string; auto_approve_enabled: boolean; streak_threshold: number; current_streak: number };

function ProposalCard({ p, canDecide, tz, onDone }: { p: Proposal; canDecide: boolean; tz: string; onDone: (result: Proposal) => void }) {
  const [reason, setReason] = useState("");
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(JSON.stringify(p.args, null, 2));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function decide(verdict: "approve" | "reject") {
    setBusy(true);
    setError(null);
    try {
      let edited_args: unknown;
      if (verdict === "approve" && editing) {
        try {
          edited_args = JSON.parse(draft);
        } catch {
          throw new Error("The edited message is not valid JSON");
        }
      }
      onDone(await api<Proposal>(`approvals/${p.id}/decide`, { body: { verdict, reason: reason || undefined, edited_args } }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="font-medium">{p.summary}</div>
          <div className="text-xs text-zinc-500">
            #{p.id} · {p.tool} · {fmtDate(p.created_at, tz)}{p.agent_run_id ? ` · from agent run #${p.agent_run_id}` : " · proposed by a person"}
          </div>
        </div>
        <div className="flex gap-1">
          <Badge tone={statusTone(p.status)}>{p.status}</Badge>
          {p.edited && <Badge tone="blue">edited</Badge>}
          {p.auto_approved && <Badge tone="blue">auto</Badge>}
        </div>
      </div>
      <div className="mt-3">
        {editing ? <Textarea rows={8} value={draft} onChange={(e) => setDraft(e.target.value)} className="font-mono text-xs" /> : <Pre>{JSON.stringify(p.final_args ?? p.args, null, 2)}</Pre>}
      </div>
      {p.decision_reason && <p className="mt-2 text-sm"><span className="text-zinc-500">Reason:</span> {p.decision_reason}</p>}
      {p.error && <p className="mt-2 text-sm text-red-600">Error: {p.error}</p>}
      {p.status === "pending" && canDecide && (
        <div className="mt-3 space-y-2">
          <Input placeholder="Reason (required to reject; helps the OS learn)" value={reason} onChange={(e) => setReason(e.target.value)} />
          <ErrorBox error={error} />
          <div className="flex flex-wrap gap-2">
            <Button disabled={busy} onClick={() => decide("approve")}>{editing ? "Approve edited version" : "Approve & run"}</Button>
            <Button variant="secondary" disabled={busy} onClick={() => setEditing(!editing)}>{editing ? "Cancel edit" : "Edit"}</Button>
            <Button variant="danger" disabled={busy} onClick={() => decide("reject")}>Reject</Button>
          </div>
        </div>
      )}
    </Card>
  );
}

export default function ApprovalsPage() {
  const me = useMe();
  const [filter, setFilter] = useState("pending");
  const [items, setItems] = useState<Proposal[] | null>(null);
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<Proposal | null>(null);
  const latest = useRef(0);
  const canDecide = can(me, "approvals.decide");

  const load = useCallback(async () => {
    const req = ++latest.current; // ignore responses from superseded requests (filter changed mid-flight)
    try {
      const [list, pol] = await Promise.all([api<Proposal[]>(`approvals?status=${filter}`), api<Policy[]>("approvals-policies")]);
      if (req !== latest.current) return;
      setItems(list);
      setPolicies(pol);
    } catch (e) {
      if (req === latest.current) setError((e as Error).message);
    }
  }, [filter]);

  const decided = (result: Proposal) => {
    setOutcome(result);
    load();
  };

  useEffect(() => {
    load();
  }, [load]);

  async function savePolicy(p: Policy, enabled: boolean, threshold: number) {
    try {
      await api(`approvals-policies/${p.tool}`, { method: "PUT", body: { auto_approve_enabled: enabled, streak_threshold: threshold } });
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <>
      <PageHeader
        title="Approvals"
        subtitle="Everything that leaves the company (emails, WhatsApp messages) waits here until you approve it. Edits and rejections are recorded as feedback."
        actions={
          <div className="w-40">
            <Select value={filter} onChange={(e) => setFilter(e.target.value)}>
              {["pending", "executed", "failed", "rejected", "all"].map((s) => <option key={s}>{s}</option>)}
            </Select>
          </div>
        }
      />
      <ErrorBox error={error} />
      {outcome && (
        <div className={`mb-3 rounded-md border px-3 py-2 text-sm ${outcome.status === "executed" ? "border-emerald-300 bg-emerald-50 text-emerald-900 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-300" : outcome.status === "failed" ? "border-red-300 bg-red-50 text-red-900 dark:border-red-900 dark:bg-red-950 dark:text-red-300" : "border-zinc-300 bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900"}`}>
          #{outcome.id} {outcome.summary}: <strong>{outcome.status}</strong>{outcome.error ? ` (${outcome.error})` : ""}
        </div>
      )}
      <div className="space-y-3">
        {items === null ? <Card><Empty>Loading…</Empty></Card> : items.length === 0 ? <Card><Empty>No {filter === "all" ? "" : filter} proposals.</Empty></Card> : items.map((p) => (
          <ProposalCard key={p.id} p={p} canDecide={canDecide} tz={me.workspace.timezone} onDone={decided} />
        ))}
      </div>

      <h2 className="mb-2 mt-8 text-sm font-semibold">Autonomy policies</h2>
      <Card>
        <p className="mb-3 text-sm text-zinc-500">
          A tool can run without asking only if you switch it on here and its most recent approvals were unedited, for at least the threshold number in a row. Any edit or rejection resets the streak.
        </p>
        <table className="w-full text-sm">
          <thead><tr className="text-left text-xs text-zinc-500"><th className="py-1">Tool</th><th>Streak</th><th>Threshold</th><th>Auto-approve</th></tr></thead>
          <tbody>
            {policies.map((p) => (
              <tr key={p.tool} className="border-t border-zinc-100 dark:border-zinc-800">
                <td className="py-2 font-mono text-xs">{p.tool}</td>
                <td>{p.current_streak}</td>
                <td>
                  <div className="w-24"><Input type="number" min={5} defaultValue={p.streak_threshold} disabled={!can(me, "autonomy.manage")}
                    onBlur={(e) => Number(e.target.value) !== p.streak_threshold && savePolicy(p, p.auto_approve_enabled, Number(e.target.value))} /></div>
                </td>
                <td>
                  <input type="checkbox" checked={p.auto_approve_enabled} disabled={!can(me, "autonomy.manage")}
                    onChange={(e) => savePolicy(p, e.target.checked, p.streak_threshold)} />
                  {p.auto_approve_enabled && p.current_streak < p.streak_threshold && <span className="ml-2 text-xs text-zinc-500">(not yet earned)</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {can(me, "approvals.propose") && <ProposeForm onDone={load} />}
    </>
  );
}

function ProposeForm({ onDone }: { onDone: () => void }) {
  const [tool, setTool] = useState("send_email");
  const [to, setTo] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const args = tool === "send_email" ? { to, subject, body } : { to, body };
    try {
      await api("approvals", { body: { tool, args } });
      setTo(""); setSubject(""); setBody("");
      onDone();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <>
      <h2 className="mb-2 mt-8 text-sm font-semibold">Draft an outgoing message</h2>
      <Card>
        <form onSubmit={submit} className="grid gap-3 md:grid-cols-2">
          <Label text="Channel">
            <Select value={tool} onChange={(e) => setTool(e.target.value)}>
              <option value="send_email">Email</option>
              <option value="send_whatsapp">WhatsApp</option>
            </Select>
          </Label>
          <Label text={tool === "send_email" ? "To (email)" : "To (phone, e.g. 0712345678)"}><Input value={to} onChange={(e) => setTo(e.target.value)} required /></Label>
          {tool === "send_email" && <Label text="Subject"><Input value={subject} onChange={(e) => setSubject(e.target.value)} required /></Label>}
          <div className="md:col-span-2"><Label text="Message"><Textarea rows={4} value={body} onChange={(e) => setBody(e.target.value)} required /></Label></div>
          <div className="md:col-span-2 space-y-2">
            <ErrorBox error={error} />
            <Button type="submit">Submit for approval</Button>
          </div>
        </form>
      </Card>
    </>
  );
}
