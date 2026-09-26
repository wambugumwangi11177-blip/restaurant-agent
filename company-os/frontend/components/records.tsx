"use client";
// Schema-driven records UI: every record type (kernel or department) renders from
// GET /records-types, so a new department needs no new frontend code.
import { useCallback, useEffect, useRef, useState } from "react";
import { api, fmtDate } from "@/lib/api";
import { Badge, Button, Card, Empty, ErrorBox, Input, Label, Select, statusTone, Textarea } from "@/components/ui";

export type FieldSpec = {
  name: string; label: string; type: string; format: string | null; options: string[] | null; required: boolean;
  default: unknown; max_length: number | null; money: boolean; long: boolean;
};
export type TypeSpec = {
  name: string; label: string; department: string; title_field: string; refs: Record<string, string>;
  can_write: boolean; can_delete: boolean; fields: FieldSpec[]; patch_fields: string[];
};
type Row = Record<string, unknown> & { id: number };
type Option = { id: number; label: string };

const STATUS_FIELDS = ["status", "stage", "priority", "severity"];

function fmtValue(f: FieldSpec | undefined, name: string, v: unknown, row: Row, tz: string): string {
  if (v === null || v === undefined || v === "") return "—";
  if (f?.money || name.endsWith("_minor")) {
    const cur = typeof row.currency === "string" ? row.currency : "";
    return `${cur} ${(Number(v) / 100).toLocaleString("en-KE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`.trim();
  }
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (typeof v === "string" && /^\d{4}-\d{2}-\d{2}/.test(v)) return fmtDate(v, tz);
  return String(v);
}

// null = still loading. A ref field whose options can't be loaded (no permission)
// is absent from the loaded map and falls back to a plain id input.
function useRefOptions(spec: TypeSpec) {
  const [opts, setOpts] = useState<Record<string, Option[]> | null>(null);
  useEffect(() => {
    const load = async () => {
      const out: Record<string, Option[]> = {};
      const types = await api<TypeSpec[]>("records-types").catch(() => [] as TypeSpec[]);
      for (const [field, target] of Object.entries(spec.refs)) {
        try {
          if (target === "user") {
            const members = await api<{ user_id: number; full_name: string }[]>("members");
            out[field] = members.map((m) => ({ id: m.user_id, label: m.full_name }));
          } else if (target === "document") {
            const docs = await api<{ id: number; title: string }[]>("memory/documents");
            out[field] = docs.map((d) => ({ id: d.id, label: d.title }));
          } else {
            const t = types.find((x) => x.name === target);
            if (!t) continue; // no read access or department disabled
            const rows = await api<Row[]>(`records/${target}?limit=200`);
            out[field] = rows.map((r) => ({ id: r.id, label: `#${r.id} ${String(r[t.title_field] ?? "")}` }));
          }
        } catch {
          /* no permission for the referenced type: fall back to a number input */
        }
      }
      setOpts(out);
    };
    load();
  }, [spec]);
  return opts;
}

function FieldInput({ f, value, onChange, options, loading }: { f: FieldSpec; value: string; onChange: (v: string) => void; options?: Option[]; loading?: boolean }) {
  if (loading) {
    return <Select disabled><option>Loading…</option></Select>;
  }
  if (options) {
    return (
      <Select value={value} onChange={(e) => onChange(e.target.value)} required={f.required}>
        <option value="">—</option>
        {options.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
      </Select>
    );
  }
  if (f.options) {
    return (
      <Select value={value || String(f.default ?? f.options[0])} onChange={(e) => onChange(e.target.value)}>
        {f.options.map((o) => <option key={o}>{o}</option>)}
      </Select>
    );
  }
  if (f.type === "boolean") {
    return <input type="checkbox" checked={value === "true"} onChange={(e) => onChange(e.target.checked ? "true" : "false")} />;
  }
  if (f.long) return <Textarea rows={3} value={value} onChange={(e) => onChange(e.target.value)} required={f.required} />;
  const type = f.format === "date" ? "date" : f.format === "date-time" ? "datetime-local" : f.money || f.type === "integer" || f.type === "number" ? "number" : "text";
  return <Input type={type} step={f.money ? "0.01" : undefined} value={value} onChange={(e) => onChange(e.target.value)} required={f.required} maxLength={f.max_length ?? undefined} />;
}

function toPayload(fields: FieldSpec[], form: Record<string, string>, refs: Record<string, string>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const f of fields) {
    const raw = form[f.name];
    if (raw === undefined || raw === "") continue;
    if (f.money) out[f.name] = Math.round(Number(raw) * 100);
    else if (f.type === "integer" || f.name in refs) out[f.name] = parseInt(raw, 10);
    else if (f.type === "number") out[f.name] = Number(raw);
    else if (f.type === "boolean") out[f.name] = raw === "true";
    else if (f.format === "date-time") out[f.name] = new Date(raw).toISOString();
    else out[f.name] = raw;
  }
  return out;
}

export function RecordsPanel({ spec, tz }: { spec: TypeSpec; tz: string }) {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [q, setQ] = useState("");
  const [form, setForm] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const latest = useRef(0);
  const refOptions = useRefOptions(spec);
  const byName = Object.fromEntries(spec.fields.map((f) => [f.name, f]));
  const statusField = STATUS_FIELDS.find((s) => spec.patch_fields.includes(s) && byName[s]?.options);
  // Row summary: amounts first (including computed ones like total_minor), then other short fields.
  const plain = spec.fields.filter((f) => f.name !== spec.title_field && !f.long && f.name !== statusField && !f.money && !(f.name in spec.refs));
  const moneyKeys = (row: Row) => Object.keys(row).filter((k) => k.endsWith("_minor") && row[k] !== null).slice(0, 3);
  const label = (k: string) => (byName[k]?.label ?? k.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase())).replace(/ minor$/i, "");

  const load = useCallback(async () => {
    const req = ++latest.current;
    try {
      const data = await api<Row[]>(`records/${spec.name}${q ? `?q=${encodeURIComponent(q)}` : ""}`);
      if (req === latest.current) { setRows(data); setError(null); }
    } catch (e) {
      if (req === latest.current) setError((e as Error).message);
    }
  }, [spec.name, q]);

  useEffect(() => { setRows(null); load(); }, [load]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api(`records/${spec.name}`, { body: toPayload(spec.fields, form, spec.refs) });
      setForm({}); setShowForm(false); load();
    } catch (err) { setError((err as Error).message); }
  }
  async function patch(id: number, body: Record<string, unknown>) {
    try { await api(`records/${spec.name}/${id}`, { method: "PATCH", body }); load(); } catch (err) { setError((err as Error).message); }
  }
  async function remove(id: number) {
    if (!confirm("Delete this record? The audit log keeps a record of the deletion.")) return;
    try { await api(`records/${spec.name}/${id}`, { method: "DELETE" }); load(); } catch (err) { setError((err as Error).message); }
  }

  return (
    <div className="space-y-3">
      <ErrorBox error={error} />
      <div className="flex flex-wrap gap-2">
        <div className="min-w-0 flex-1"><Input placeholder={`Search ${spec.label.toLowerCase()}…`} value={q} onChange={(e) => setQ(e.target.value)} /></div>
        {spec.can_write && <Button variant={showForm ? "secondary" : "primary"} onClick={() => setShowForm(!showForm)}>{showForm ? "Close" : "New"}</Button>}
      </div>
      {showForm && (
        <Card>
          <form onSubmit={create} className="grid gap-3 md:grid-cols-2">
            {spec.fields.map((f) => (
              <div key={f.name} className={f.long ? "md:col-span-2" : ""}>
                <Label text={`${f.money ? f.label.replace(/ minor$/i, "") + " (e.g. 1500.00)" : f.label}${f.required ? " *" : ""}`}>
                  <FieldInput f={f} value={form[f.name] ?? ""} options={refOptions?.[f.name]} loading={refOptions === null && f.name in spec.refs}
                    onChange={(v) => setForm({ ...form, [f.name]: v })} />
                </Label>
              </div>
            ))}
            <div className="md:col-span-2"><Button type="submit" disabled={refOptions === null}>Create</Button></div>
          </form>
        </Card>
      )}
      <Card>
        {rows === null ? <Empty>Loading…</Empty> : rows.length === 0 ? <Empty>No {spec.label.toLowerCase()} {q ? "match" : "yet"}.</Empty> : (
          <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {rows.map((r) => (
              <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
                <div className="min-w-0">
                  <div className="font-medium">#{r.id} {String(r[spec.title_field] ?? "")}</div>
                  <div className="flex flex-wrap gap-x-3 text-xs text-zinc-500">
                    {moneyKeys(r).map((k) => <span key={k}>{label(k)}: {fmtValue(undefined, k, r[k], r, tz)}</span>)}
                    {plain.slice(0, 3).map((c) => <span key={c.name}>{c.label}: {fmtValue(c, c.name, r[c.name], r, tz)}</span>)}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {statusField && (spec.can_write ? (
                    <div className="w-36">
                      <Select value={String(r[statusField])} onChange={(e) => patch(r.id, { [statusField]: e.target.value })}>
                        {byName[statusField].options!.map((o) => <option key={o}>{o}</option>)}
                      </Select>
                    </div>
                  ) : <Badge tone={statusTone(String(r[statusField]))}>{String(r[statusField])}</Badge>)}
                  {spec.can_delete && <Button variant="secondary" onClick={() => remove(r.id)}>Delete</Button>}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
