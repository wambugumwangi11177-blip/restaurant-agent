"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { RecordsPanel, type TypeSpec } from "@/components/records";
import { can, useMe } from "@/components/shell";
import { Button, Card, Empty, ErrorBox, Input, PageHeader, Pre } from "@/components/ui";

type Dept = {
  key: string; label: string; description: string; directive: string; record_types: string[];
  reports: { key: string; label: string; description: string; params: string[] }[];
  agents: string[]; jobs: { name: string; schedule: string }[];
};
type ReportOut = { title: string; summary: string; columns: string[]; rows: unknown[][] };

function ReportRunner({ r }: { r: Dept["reports"][number] }) {
  const [params, setParams] = useState<Record<string, string>>({});
  const [out, setOut] = useState<ReportOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  async function run() {
    setError(null);
    try {
      const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v));
      setOut(await api<ReportOut>(`reports/${r.key}${qs.toString() ? `?${qs}` : ""}`));
    } catch (e) { setError((e as Error).message); }
  }
  return (
    <Card>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">{r.label}</span>
        {r.params.map((p) => (
          <div key={p} className="w-40"><Input placeholder={p} value={params[p] ?? ""} onChange={(e) => setParams({ ...params, [p]: e.target.value })} /></div>
        ))}
        <Button variant="secondary" onClick={run}>Run</Button>
      </div>
      <ErrorBox error={error} />
      {out && (
        <div className="mt-3 space-y-2">
          {out.summary && (out.columns.length === 0 ? <Pre>{out.summary}</Pre> : <p className="text-sm text-zinc-600 dark:text-zinc-400">{out.summary}</p>)}
          {out.columns.length > 0 && (out.rows.length === 0 ? <Empty>Nothing to show.</Empty> : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="text-left text-xs text-zinc-500">{out.columns.map((c) => <th key={c} className="py-1 pr-3">{c}</th>)}</tr></thead>
                <tbody>{out.rows.map((row, i) => (
                  <tr key={i} className="border-t border-zinc-100 dark:border-zinc-800">{row.map((cell, j) => <td key={j} className="py-1.5 pr-3">{String(cell)}</td>)}</tr>
                ))}</tbody>
              </table>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

export default function DepartmentPage() {
  const me = useMe();
  const { dept } = useParams<{ dept: string }>();
  const [d, setD] = useState<Dept | null>(null);
  const [types, setTypes] = useState<TypeSpec[]>([]);
  const [tab, setTab] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [jobOut, setJobOut] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [depts, t] = await Promise.all([api<Dept[]>("departments"), api<TypeSpec[]>("records-types")]);
        const found = depts.find((x) => x.key === dept) ?? null;
        setD(found);
        setTypes(t);
        if (found) setTab(found.record_types[0] ?? "");
        if (!found) setError("This department is not available to you.");
      } catch (e) { setError((e as Error).message); }
    })();
  }, [dept]);

  if (!d) return <><PageHeader title="Department" /><ErrorBox error={error} />{!error && <Empty>Loading…</Empty>}</>;
  const spec = types.find((t) => t.name === tab);

  return (
    <>
      <PageHeader title={d.label} subtitle={d.description} />
      <div className="mb-4 flex flex-wrap gap-2">
        {d.record_types.map((t) => (
          <Button key={t} variant={t === tab ? "primary" : "secondary"} onClick={() => setTab(t)}>
            {types.find((x) => x.name === t)?.label ?? t}
          </Button>
        ))}
      </div>
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">{spec ? <RecordsPanel key={spec.name} spec={spec} tz={me.workspace.timezone} /> : <Empty>Pick a record type.</Empty>}</div>
        <div className="space-y-4">
          {d.reports.length > 0 && <h2 className="text-sm font-semibold">Reports</h2>}
          {d.reports.map((r) => <ReportRunner key={r.key} r={r} />)}
          {d.agents.length > 0 && (
            <Card>
              <h2 className="mb-2 text-sm font-semibold">Agents</h2>
              <ul className="space-y-1 text-sm">{d.agents.map((a) => <li key={a}><Link className="underline" href={`/agents?agent=${a}`}>{a}</Link></li>)}</ul>
            </Card>
          )}
          {d.jobs.length > 0 && can(me, "jobs.run") && (
            <Card>
              <h2 className="mb-2 text-sm font-semibold">Scheduled jobs</h2>
              {d.jobs.map((j) => (
                <div key={j.name} className="mb-2 flex items-center justify-between gap-2 text-sm">
                  <span>{j.name} <span className="text-xs text-zinc-500">({j.schedule})</span></span>
                  <Button variant="secondary" onClick={async () => {
                    try { setJobOut((await api<{ summary: string }>(`jobs/${j.name}/run`, { method: "POST" })).summary); }
                    catch (e) { setError((e as Error).message); }
                  }}>Run now</Button>
                </div>
              ))}
              {jobOut && <p className="text-xs text-zinc-500">{jobOut}</p>}
            </Card>
          )}
          <p className="text-xs text-zinc-500">How this department works: <code>{d.directive}</code></p>
        </div>
      </div>
      <ErrorBox error={error} />
    </>
  );
}
