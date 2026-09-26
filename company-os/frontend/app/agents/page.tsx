"use client";
import { useCallback, useEffect, useState } from "react";
import { api, fmtDate, usd } from "@/lib/api";
import { can, useMe } from "@/components/shell";
import { Badge, Button, Card, Empty, ErrorBox, PageHeader, Pre, statusTone, Textarea } from "@/components/ui";

type Agent = { name: string; description: string; uses_llm: boolean; has_fallback: boolean; input_hint: string; tools: { name: string; effect: string }[] };
type Citation = { document_title: string; heading: string; snippet: string };
type ToolCall = { id: number; tool: string; effect: string; status: string; args: unknown; proposal_id: number | null };
type Run = {
  id: number; agent: string; status: string; input: string; output: string | null; error: string | null; citations: Citation[];
  model: string | null; input_tokens: number; output_tokens: number; cost_usd: string; latency_ms: number | null; created_at: string; tool_calls?: ToolCall[];
};

function RunView({ run, tz }: { run: Run; tz: string }) {
  const [sent, setSent] = useState<string | null>(null);
  async function feedback(verdict: "helpful" | "unhelpful") {
    const reason = verdict === "unhelpful" ? prompt("What was wrong? (this becomes a learning signal)") ?? undefined : undefined;
    await api(`agents/runs/${run.id}/feedback`, { body: { verdict, reason } });
    setSent(verdict);
  }
  return (
    <Card>
      <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-zinc-500">
        <Badge tone={statusTone(run.status)}>{run.status}</Badge>
        <span>{run.agent} · run #{run.id} · {fmtDate(run.created_at, tz)}</span>
        <span>{run.model} · {run.input_tokens + run.output_tokens} tokens · {usd(run.cost_usd)} · {run.latency_ms} ms</span>
      </div>
      {run.output && <Pre>{run.output}</Pre>}
      {run.error && <p className="mt-2 text-sm text-red-600">{run.error}</p>}
      {run.citations.length > 0 && (
        <div className="mt-3">
          <div className="mb-1 text-xs font-semibold text-zinc-500">Sources</div>
          <ol className="list-decimal space-y-1 pl-5 text-xs">
            {run.citations.map((c, i) => <li key={i}><span className="font-medium">{c.heading}</span></li>)}
          </ol>
        </div>
      )}
      {run.tool_calls && run.tool_calls.length > 0 && (
        <div className="mt-3 text-xs">
          <div className="mb-1 font-semibold text-zinc-500">Tool calls</div>
          {run.tool_calls.map((t) => (
            <div key={t.id} className="flex gap-2">
              <Badge tone={statusTone(t.status)}>{t.status}</Badge><span className="font-mono">{t.tool}</span><span className="text-zinc-500">{t.effect}</span>
              {t.proposal_id && <a href={`/approvals?focus=${t.proposal_id}`} className="underline">proposal #{t.proposal_id}</a>}
            </div>
          ))}
        </div>
      )}
      <div className="mt-3 flex gap-2 text-xs">
        {sent ? <span className="text-zinc-500">Feedback recorded ({sent}).</span> : (
          <>
            <button className="underline" onClick={() => feedback("helpful")}>Helpful</button>
            <button className="underline" onClick={() => feedback("unhelpful")}>Not helpful</button>
          </>
        )}
      </div>
    </Card>
  );
}

export default function AgentsPage() {
  const me = useMe();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [provider, setProvider] = useState<string | null>(null);
  const [selected, setSelected] = useState(() =>
    typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("agent") ?? "memory_qa" : "memory_qa");
  const [input, setInput] = useState("");
  const [result, setResult] = useState<Run | null>(null);
  const [runs, setRuns] = useState<Run[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const a = await api<{ llm_provider: string | null; agents: Agent[] }>("agents");
      setAgents(a.agents);
      setProvider(a.llm_provider);
      if (can(me, "agents.read_runs")) setRuns(await api<Run[]>("agents/runs?limit=20"));
    } catch (e) {
      setError((e as Error).message);
    }
  }, [me]);

  useEffect(() => {
    load();
  }, [load]);

  async function run(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setResult(await api<Run>(`agents/${selected}/run`, { body: { input } }));
      load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const agent = agents.find((a) => a.name === selected);
  return (
    <>
      <PageHeader title="Agents" subtitle={`LLM provider: ${provider ?? "none configured (agents with a fallback still work)"}. Every run is logged with its tool calls, tokens and cost.`} />
      <ErrorBox error={error} />
      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <ul className="space-y-2">
            {agents.map((a) => (
              <li key={a.name}>
                <button onClick={() => setSelected(a.name)} className={`w-full rounded-md p-2 text-left text-sm ${a.name === selected ? "bg-zinc-100 dark:bg-zinc-800" : "hover:bg-zinc-50 dark:hover:bg-zinc-800"}`}>
                  <div className="font-medium">{a.name} {a.uses_llm ? <Badge tone="blue">LLM</Badge> : <Badge>deterministic</Badge>}</div>
                  <div className="text-xs text-zinc-500">{a.description}</div>
                  {a.tools.length > 0 && <div className="mt-1 text-xs text-zinc-400">tools: {a.tools.map((t) => `${t.name} (${t.effect})`).join(", ")}</div>}
                </button>
              </li>
            ))}
          </ul>
        </Card>
        <div className="space-y-4 lg:col-span-2">
          <Card>
            <form onSubmit={run} className="space-y-2">
              <Textarea rows={3} placeholder={agent?.input_hint || "Input"} value={input} onChange={(e) => setInput(e.target.value)} />
              <Button type="submit" disabled={busy}>{busy ? "Running…" : `Run ${selected}`}</Button>
            </form>
          </Card>
          {result && <RunView run={result} tz={me.workspace.timezone} />}
          <h2 className="text-sm font-semibold">Recent runs</h2>
          {runs === null ? <Card><Empty>Loading…</Empty></Card> : runs.length === 0 ? <Card><Empty>No runs yet.</Empty></Card> : runs.map((r) => <RunView key={r.id} run={r} tz={me.workspace.timezone} />)}
        </div>
      </div>
    </>
  );
}
