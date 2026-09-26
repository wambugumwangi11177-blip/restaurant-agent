"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, fmtDate } from "@/lib/api";
import { can, useMe } from "@/components/shell";
import { Badge, Button, Card, Empty, ErrorBox, Input, Label, PageHeader, Select, statusTone, Textarea } from "@/components/ui";

type Field = { name: string; label: string; kind?: "text" | "long" | "date" | "select"; options?: string[]; required?: boolean };
type Row = Record<string, unknown> & { id: number };

const TYPES: Record<string, { label: string; title: string; fields: Field[]; columns: string[] }> = {
  task: {
    label: "Tasks", title: "title", columns: ["status", "priority", "due_date"],
    fields: [
      { name: "title", label: "Title", required: true },
      { name: "description", label: "Description", kind: "long" },
      { name: "priority", label: "Priority", kind: "select", options: ["normal", "low", "high", "urgent"] },
      { name: "due_date", label: "Due date", kind: "date" },
    ],
  },
  decision: {
    label: "Decisions", title: "title", columns: ["status", "revisit_on"],
    fields: [
      { name: "title", label: "Title", required: true },
      { name: "decision", label: "What we decided", kind: "long", required: true },
      { name: "context", label: "Context", kind: "long" },
      { name: "alternatives", label: "Alternatives considered", kind: "long" },
      { name: "rationale", label: "Why", kind: "long" },
      { name: "revisit_on", label: "Revisit on", kind: "date" },
    ],
  },
  person: {
    label: "People", title: "full_name", columns: ["title", "email", "phone"],
    fields: [
      { name: "full_name", label: "Full name", required: true },
      { name: "title", label: "Role / title" },
      { name: "email", label: "Email" },
      { name: "phone", label: "Phone" },
      { name: "notes", label: "Notes", kind: "long" },
    ],
  },
  organization: {
    label: "Organizations", title: "name", columns: ["industry", "website"],
    fields: [
      { name: "name", label: "Name", required: true },
      { name: "industry", label: "Industry" },
      { name: "website", label: "Website" },
      { name: "notes", label: "Notes", kind: "long" },
    ],
  },
  note: {
    label: "Notes", title: "title", columns: ["created_at"],
    fields: [
      { name: "title", label: "Title", required: true },
      { name: "body", label: "Body", kind: "long" },
    ],
  },
};

export default function RecordsPage() {
  const me = useMe();
  const [type, setType] = useState("task");
  const [rows, setRows] = useState<Row[] | null>(null);
  const [q, setQ] = useState("");
  const [form, setForm] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const spec = TYPES[type];
  const writable = can(me, "records.write");

  const latest = useRef(0);

  const load = useCallback(async () => {
    const req = ++latest.current; // typing in search fires overlapping requests; keep only the newest
    try {
      const data = await api<Row[]>(`records/${type}${q ? `?q=${encodeURIComponent(q)}` : ""}`);
      if (req !== latest.current) return;
      setRows(data);
      setError(null);
    } catch (e) {
      if (req === latest.current) setError((e as Error).message);
    }
  }, [type, q]);

  useEffect(() => {
    load();
  }, [load]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    const body = Object.fromEntries(Object.entries(form).filter(([, v]) => v !== ""));
    try {
      await api(`records/${type}`, { body });
      setForm({});
      load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function patch(id: number, body: Record<string, unknown>) {
    try {
      await api(`records/${type}/${id}`, { method: "PATCH", body });
      load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function remove(id: number) {
    if (!confirm("Delete this record? The audit log keeps a record of the deletion.")) return;
    try {
      await api(`records/${type}/${id}`, { method: "DELETE" });
      load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <>
      <PageHeader title="Records" subtitle="The shared core every department builds on. Every change is audited." />
      <div className="mb-4 flex flex-wrap gap-2">
        {Object.entries(TYPES).map(([k, v]) => (
          <Button key={k} variant={k === type ? "primary" : "secondary"} onClick={() => { setType(k); setForm({}); setQ(""); setRows(null); }}>{v.label}</Button>
        ))}
      </div>
      <ErrorBox error={error} />
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <Input placeholder={`Search ${spec.label.toLowerCase()}…`} value={q} onChange={(e) => setQ(e.target.value)} className="mb-3" />
          {rows === null ? <Empty>Loading…</Empty> : rows.length === 0 ? <Empty>No {spec.label.toLowerCase()} {q ? "match" : "yet"}.</Empty> : (
            <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
              {rows.map((r) => (
                <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
                  <div className="min-w-0">
                    <div className="font-medium">{String(r[spec.title] ?? "")}</div>
                    <div className="flex flex-wrap gap-2 text-xs text-zinc-500">
                      {spec.columns.map((c) => r[c] ? (
                        c === "status" ? <Badge key={c} tone={statusTone(String(r[c]))}>{String(r[c])}</Badge>
                          : <span key={c}>{c.endsWith("_on") || c.endsWith("_date") || c.endsWith("_at") ? fmtDate(String(r[c]), me.workspace.timezone) : String(r[c])}</span>
                      ) : null)}
                    </div>
                  </div>
                  <div className="flex gap-2">
                    {type === "task" && writable && (
                      <div className="w-32">
                        <Select value={String(r.status)} onChange={(e) => patch(r.id, { status: e.target.value })}>
                          {["open", "in_progress", "done", "cancelled"].map((s) => <option key={s}>{s}</option>)}
                        </Select>
                      </div>
                    )}
                    {can(me, "records.delete") && <Button variant="secondary" onClick={() => remove(r.id)}>Delete</Button>}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
        {writable && (
          <Card>
            <h2 className="mb-3 text-sm font-semibold">New {spec.label.slice(0, -1).toLowerCase()}</h2>
            <form onSubmit={create} className="space-y-3">
              {spec.fields.map((f) => (
                <Label key={f.name} text={f.label + (f.required ? " *" : "")}>
                  {f.kind === "long" ? <Textarea rows={3} value={form[f.name] ?? ""} onChange={(e) => setForm({ ...form, [f.name]: e.target.value })} required={f.required} />
                    : f.kind === "select" ? (
                      <Select value={form[f.name] ?? f.options![0]} onChange={(e) => setForm({ ...form, [f.name]: e.target.value })}>
                        {f.options!.map((o) => <option key={o}>{o}</option>)}
                      </Select>
                    ) : <Input type={f.kind === "date" ? "date" : "text"} value={form[f.name] ?? ""} onChange={(e) => setForm({ ...form, [f.name]: e.target.value })} required={f.required} />}
                </Label>
              ))}
              <Button type="submit">Create</Button>
            </form>
          </Card>
        )}
      </div>
    </>
  );
}
