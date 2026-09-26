"use client";
import { useCallback, useEffect, useState } from "react";
import { api, fmtDate } from "@/lib/api";
import { useMe } from "@/components/shell";
import { Badge, Button, Card, Empty, ErrorBox, Input, PageHeader } from "@/components/ui";

type Row = { id: number; action: string; entity_type: string | null; entity_id: number | null; changes: Record<string, unknown>; actor_user_id: number | null; actor_agent_run_id: number | null; request_id: string | null; created_at: string };

export default function AuditPage() {
  const me = useMe();
  const [rows, setRows] = useState<Row[] | null>(null);
  const [entity, setEntity] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (beforeId?: number) => {
    try {
      const qs = new URLSearchParams({ limit: "100" });
      if (entity) qs.set("entity_type", entity);
      if (beforeId) qs.set("before_id", String(beforeId));
      const page = await api<Row[]>(`audit?${qs}`);
      setRows((prev) => (beforeId && prev ? [...prev, ...page] : page));
    } catch (e) {
      setError((e as Error).message);
    }
  }, [entity]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <>
      <PageHeader title="Audit log" subtitle="Append-only: the database rejects edits and deletes. Personal data is recorded only as “changed”, never its value." />
      <ErrorBox error={error} />
      <Card>
        <Input placeholder="Filter by entity type (task, person, proposal, document, user…)" value={entity} onChange={(e) => setEntity(e.target.value.trim())} className="mb-3" />
        {rows === null ? <Empty>Loading…</Empty> : rows.length === 0 ? <Empty>No entries.</Empty> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-xs text-zinc-500"><th className="py-1 pr-3">When</th><th className="pr-3">Action</th><th className="pr-3">Entity</th><th className="pr-3">Actor</th><th>Changes</th></tr></thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="border-t border-zinc-100 align-top dark:border-zinc-800">
                    <td className="whitespace-nowrap py-1.5 pr-3 text-xs text-zinc-500">{fmtDate(r.created_at, me.workspace.timezone)}</td>
                    <td className="pr-3"><Badge>{r.action}</Badge></td>
                    <td className="whitespace-nowrap pr-3">{r.entity_type ? `${r.entity_type} #${r.entity_id}` : "—"}</td>
                    <td className="whitespace-nowrap pr-3 text-xs">{r.actor_agent_run_id ? `agent run #${r.actor_agent_run_id}` : r.actor_user_id ? `user #${r.actor_user_id}` : "system"}</td>
                    <td className="font-mono text-xs break-all">{Object.keys(r.changes).length ? JSON.stringify(r.changes) : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {rows && rows.length >= 100 && <Button variant="secondary" className="mt-3" onClick={() => load(rows[rows.length - 1].id)}>Load older</Button>}
      </Card>
    </>
  );
}
