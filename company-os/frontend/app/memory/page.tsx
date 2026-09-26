"use client";
import { useCallback, useEffect, useState } from "react";
import { api, fmtDate } from "@/lib/api";
import { can, useMe } from "@/components/shell";
import { Button, Card, Empty, ErrorBox, Input, Label, PageHeader, Textarea } from "@/components/ui";

type Doc = { id: number; title: string; source: string | null; created_at: string; chars: number; chunks?: number };
type Hit = { document_id: number; document_title: string; chunk_index: number; heading: string; snippet: string; score: number };

function Snippet({ text }: { text: string }) {
  // The API marks matches with « » ; render them as highlights without using innerHTML.
  const parts = text.split(/(«[^»]*»)/g);
  return <>{parts.map((p, i) => p.startsWith("«") ? <mark key={i} className="rounded bg-amber-200 px-0.5 dark:bg-amber-800">{p.slice(1, -1)}</mark> : <span key={i}>{p}</span>)}</>;
}

export default function MemoryPage() {
  const me = useMe();
  const [docs, setDocs] = useState<Doc[] | null>(null);
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<Hit[] | null>(null);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setDocs(await api<Doc[]>("memory/documents"));
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function search(e: React.FormEvent) {
    e.preventDefault();
    if (!q.trim()) return;
    try {
      setHits((await api<{ results: Hit[] }>(`memory/search?q=${encodeURIComponent(q)}&limit=8`)).results);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      let r: Doc & { created: boolean };
      if (file) {
        const form = new FormData();
        form.append("file", file);
        if (title) form.append("title", title);
        r = await api("memory/documents/upload", { form });
      } else {
        r = await api("memory/documents", { body: { title, content } });
      }
      setNotice(r.created ? `Added “${r.title}”.` : `“${r.title}” is already in memory (same content).`);
      setTitle(""); setContent(""); setFile(null);
      load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <>
      <PageHeader title="Company memory" subtitle="Documents the agents answer from. Every answer points back to a document and section." />
      <ErrorBox error={error} />
      <Card className="mb-4">
        <form onSubmit={search} className="flex gap-2">
          <Input placeholder="Search your documents…" value={q} onChange={(e) => setQ(e.target.value)} />
          <Button type="submit">Search</Button>
        </form>
        {hits && (hits.length === 0 ? <Empty>No passage matched. Try other words (search matches words, not meanings).</Empty> : (
          <ol className="mt-3 space-y-3 text-sm">
            {hits.map((h, i) => (
              <li key={`${h.document_id}-${h.chunk_index}`}>
                <div className="text-xs text-zinc-500">[{i + 1}] {h.heading}</div>
                <div><Snippet text={h.snippet} /></div>
              </li>
            ))}
          </ol>
        ))}
      </Card>
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <h2 className="mb-2 text-sm font-semibold">Documents{docs ? ` (${docs.length})` : ""}</h2>
          {docs === null ? <Empty>Loading…</Empty> : docs.length === 0 ? <Empty>No documents yet. Add your handbook, policies, client notes, SOPs.</Empty> : (
            <ul className="divide-y divide-zinc-100 text-sm dark:divide-zinc-800">
              {docs.map((d) => (
                <li key={d.id} className="flex justify-between gap-3 py-2">
                  <span className="font-medium">{d.title}</span>
                  <span className="shrink-0 text-xs text-zinc-500">{d.chunks} sections · {fmtDate(d.created_at, me.workspace.timezone)}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
        {can(me, "memory.ingest") && (
          <Card>
            <h2 className="mb-3 text-sm font-semibold">Add a document</h2>
            <form onSubmit={add} className="space-y-3">
              <Label text="Title"><Input value={title} onChange={(e) => setTitle(e.target.value)} required={!file} /></Label>
              <Label text="Upload .md or .txt"><input type="file" accept=".md,.markdown,.txt" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="text-sm" /></Label>
              {!file && <Label text="…or paste text (Markdown headings become sections)"><Textarea rows={8} value={content} onChange={(e) => setContent(e.target.value)} required /></Label>}
              {notice && <p className="text-sm text-emerald-700 dark:text-emerald-400">{notice}</p>}
              <Button type="submit">Add to memory</Button>
            </form>
          </Card>
        )}
      </div>
    </>
  );
}
