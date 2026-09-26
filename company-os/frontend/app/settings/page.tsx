"use client";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { can, useMe } from "@/components/shell";
import { Badge, Button, Card, ErrorBox, Input, Label, PageHeader, Select } from "@/components/ui";

type Setting = { key: string; department: string; description: string; secret: boolean; kind: string; is_set: boolean; value: unknown };
type Usage = { plan: string; seats_used: number; seat_limit: number | null; agent_runs_this_month: number; monthly_agent_run_limit: number | null; llm_spend_this_month_usd: string };

function WorkspaceSettings() {
  const [items, setItems] = useState<Setting[] | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [usage, setUsage] = useState<Usage | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    try {
      setItems(await api<Setting[]>("workspace/settings"));
      setUsage(await api<Usage>("workspace/usage"));
    } catch (e) { setError((e as Error).message); }
  }, []);
  useEffect(() => { load(); }, [load]);
  async function save(key: string, value: string | null) {
    setError(null); setMsg(null);
    try {
      await api("workspace/settings", { method: "PUT", body: { [key]: value } });
      setDraft({ ...draft, [key]: "" }); setMsg(`Saved ${key}`); load();
    } catch (e) { setError((e as Error).message); }
  }
  return (
    <>
      <h2 className="mb-2 mt-8 text-sm font-semibold">Workspace</h2>
      <Card>
        {usage && (
          <p className="mb-3 text-sm text-zinc-600 dark:text-zinc-400">
            Plan <strong>{usage.plan}</strong> · seats {usage.seats_used}{usage.seat_limit ? ` / ${usage.seat_limit}` : ""} ·
            agent runs this month {usage.agent_runs_this_month}{usage.monthly_agent_run_limit != null ? ` / ${usage.monthly_agent_run_limit}` : ""} ·
            LLM spend this month ${Number(usage.llm_spend_this_month_usd).toFixed(4)}
          </p>
        )}
        <ErrorBox error={error} />
        {msg && <p className="mb-2 text-sm text-emerald-700 dark:text-emerald-400">{msg}</p>}
        <div className="space-y-3">
          {items?.map((it) => (
            <div key={it.key} className="grid gap-2 md:grid-cols-3 md:items-center">
              <div className="text-sm"><div className="font-mono text-xs">{it.key}</div><div className="text-xs text-zinc-500">{it.description}</div></div>
              <Input placeholder={it.is_set ? (it.secret ? "•••••• (set — type to replace)" : String(it.value)) : "not set"}
                type={it.secret ? "password" : "text"} value={draft[it.key] ?? ""} onChange={(e) => setDraft({ ...draft, [it.key]: e.target.value })} />
              <div className="flex gap-2">
                <Button variant="secondary" disabled={!draft[it.key]} onClick={() => save(it.key, draft[it.key])}>Save</Button>
                {it.is_set && <Button variant="secondary" onClick={() => save(it.key, null)}>Clear</Button>}
              </div>
            </div>
          ))}
        </div>
      </Card>
    </>
  );
}

type Member = { user_id: number; email: string; full_name: string; phone: string | null; role: string; mfa_enabled: boolean };
const ROLES = ["founder", "staff", "contractor", "advisor"];

export default function SettingsPage() {
  const me = useMe();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [mfa, setMfa] = useState<{ secret: string; otpauth_uri: string } | null>(null);
  const [code, setCode] = useState("");
  const [pw, setPw] = useState({ current: "", next: "" });
  const [members, setMembers] = useState<Member[]>([]);
  const [invite, setInvite] = useState({ email: "", full_name: "", role: "staff", password: "", phone: "" });
  const manage = can(me, "members.manage");

  const loadMembers = useCallback(async () => {
    if (can(me, "records.read")) setMembers(await api<Member[]>("members"));
  }, [me]);

  useEffect(() => {
    loadMembers().catch((e) => setError((e as Error).message));
  }, [loadMembers]);

  const run = (fn: () => Promise<unknown>, ok?: string) => async () => {
    setError(null);
    setNotice(null);
    try {
      await fn();
      if (ok) setNotice(ok);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <>
      <PageHeader title="Settings" subtitle={`${me.user.email} · ${me.role} in ${me.workspace.name}`} />
      <ErrorBox error={error} />
      {notice && <p className="mb-3 text-sm text-emerald-700 dark:text-emerald-400">{notice}</p>}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <h2 className="mb-2 text-sm font-semibold">Two-factor authentication {me.user.mfa_enabled ? <Badge tone="green">on</Badge> : <Badge tone="amber">off</Badge>}</h2>
          {!me.user.mfa_enabled && (
            mfa ? (
              <div className="space-y-2 text-sm">
                <p>Add this key to your authenticator app (Google Authenticator, 1Password, Authy), then enter the 6-digit code.</p>
                <code className="block break-all rounded bg-zinc-100 p-2 text-xs dark:bg-zinc-950">{mfa.secret}</code>
                <Input placeholder="123456" inputMode="numeric" maxLength={6} value={code} onChange={(e) => setCode(e.target.value)} />
                <Button onClick={run(async () => { await api("auth/mfa/enable", { body: { code } }); location.reload(); })}>Turn on</Button>
              </div>
            ) : <Button onClick={run(async () => setMfa(await api("auth/mfa/setup", { method: "POST" })))}>Set up</Button>
          )}
        </Card>
        <Card>
          <h2 className="mb-2 text-sm font-semibold">Password & sessions</h2>
          <div className="space-y-2">
            <Input type="password" placeholder="Current password" autoComplete="current-password" value={pw.current} onChange={(e) => setPw({ ...pw, current: e.target.value })} />
            <Input type="password" placeholder="New password (12+ chars, upper, lower, digit)" autoComplete="new-password" value={pw.next} onChange={(e) => setPw({ ...pw, next: e.target.value })} />
            <div className="flex flex-wrap gap-2">
              <Button onClick={run(async () => { await api("auth/password", { body: { current_password: pw.current, new_password: pw.next } }); await fetch("/api/session", { method: "DELETE" }); router.push("/login"); })}>Change password</Button>
              <Button variant="secondary" onClick={run(async () => { await api("auth/logout-all", { method: "POST" }); await fetch("/api/session", { method: "DELETE" }); router.push("/login"); })}>Sign out everywhere</Button>
            </div>
          </div>
        </Card>
      </div>

      {can(me, "workspace.settings") && <WorkspaceSettings />}

      <h2 className="mb-2 mt-8 text-sm font-semibold">Members</h2>
      <Card>
        <table className="w-full text-sm">
          <thead><tr className="text-left text-xs text-zinc-500"><th className="py-1">Name</th><th>Email</th><th>WhatsApp</th><th>Role</th><th /></tr></thead>
          <tbody>
            {members.map((m) => (
              <tr key={m.user_id} className="border-t border-zinc-100 dark:border-zinc-800">
                <td className="py-2">{m.full_name} {m.mfa_enabled && <Badge tone="green">2FA</Badge>}</td>
                <td>{m.email}</td>
                <td>{m.phone ?? "—"}</td>
                <td>
                  {manage ? (
                    <div className="w-32"><Select value={m.role} onChange={(e) => run(async () => { await api(`members/${m.user_id}`, { method: "PATCH", body: { role: e.target.value } }); await loadMembers(); }, "Role updated")()}>
                      {ROLES.map((r) => <option key={r}>{r}</option>)}
                    </Select></div>
                  ) : m.role}
                </td>
                <td className="text-right">
                  {manage && m.user_id !== me.user.id && (
                    <Button variant="secondary" onClick={run(async () => { if (confirm(`Remove ${m.email}? Their sessions end immediately.`)) { await api(`members/${m.user_id}`, { method: "DELETE" }); await loadMembers(); } })}>Remove</Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {manage && (
          <form className="mt-4 grid gap-2 md:grid-cols-5" onSubmit={(e) => { e.preventDefault(); run(async () => {
            await api("members", { body: { ...invite, phone: invite.phone || undefined } });
            setInvite({ email: "", full_name: "", role: "staff", password: "", phone: "" });
            await loadMembers();
          }, "Member added. Share the password with them securely; they should change it on first sign-in.")(); }}>
            <Label text="Name"><Input value={invite.full_name} onChange={(e) => setInvite({ ...invite, full_name: e.target.value })} required /></Label>
            <Label text="Email"><Input type="email" value={invite.email} onChange={(e) => setInvite({ ...invite, email: e.target.value })} required /></Label>
            <Label text="WhatsApp (optional)"><Input value={invite.phone} onChange={(e) => setInvite({ ...invite, phone: e.target.value })} /></Label>
            <Label text="Role"><Select value={invite.role} onChange={(e) => setInvite({ ...invite, role: e.target.value })}>{ROLES.map((r) => <option key={r}>{r}</option>)}</Select></Label>
            <Label text="Temporary password"><Input type="password" autoComplete="new-password" value={invite.password} onChange={(e) => setInvite({ ...invite, password: e.target.value })} /></Label>
            <div className="md:col-span-5"><Button type="submit">Add member</Button></div>
          </form>
        )}
      </Card>
    </>
  );
}
