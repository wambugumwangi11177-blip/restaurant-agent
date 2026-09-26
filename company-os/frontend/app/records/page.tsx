"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { RecordsPanel, type TypeSpec } from "@/components/records";
import { useMe } from "@/components/shell";
import { Button, Empty, ErrorBox, PageHeader } from "@/components/ui";

export default function RecordsPage() {
  const me = useMe();
  const [types, setTypes] = useState<TypeSpec[] | null>(null);
  const [tab, setTab] = useState("task");
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api<TypeSpec[]>("records-types").then((t) => setTypes(t.filter((x) => x.department === "kernel"))).catch((e) => setError(e.message));
  }, []);
  const spec = types?.find((t) => t.name === tab);
  return (
    <>
      <PageHeader title="Records" subtitle="The shared core every department builds on. Every change is audited." />
      <ErrorBox error={error} />
      <div className="mb-4 flex flex-wrap gap-2">
        {types?.map((t) => <Button key={t.name} variant={t.name === tab ? "primary" : "secondary"} onClick={() => setTab(t.name)}>{t.label}</Button>)}
      </div>
      {types === null ? <Empty>Loading…</Empty> : spec ? <RecordsPanel key={spec.name} spec={spec} tz={me.workspace.timezone} /> : <Empty>No access.</Empty>}
    </>
  );
}
