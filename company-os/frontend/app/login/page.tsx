"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button, Card, ErrorBox, Input, Label } from "@/components/ui";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [needCode, setNeedCode] = useState(false);
  const [workspaces, setWorkspaces] = useState<string[]>([]);
  const [workspace, setWorkspace] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const r = await fetch("/api/session", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ email, password, totp_code: code || undefined, workspace_slug: workspace || undefined }),
    });
    setBusy(false);
    if (r.ok) return router.push("/");
    const data = await r.json().catch(() => ({}));
    if (data.detail === "mfa_required") {
      setNeedCode(true);
      return;
    }
    if (r.status === 409 && data.detail?.workspaces) {
      setWorkspaces(data.detail.workspaces);
      setWorkspace(data.detail.workspaces[0]);
      return;
    }
    setError(typeof data.detail === "string" ? data.detail : "Sign-in failed");
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <Card className="w-full max-w-sm">
        <h1 className="mb-1 text-lg font-semibold">Company OS</h1>
        <p className="mb-4 text-sm text-zinc-500">Sign in to your workspace.</p>
        <form onSubmit={submit} className="space-y-3">
          <Label text="Email"><Input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required /></Label>
          <Label text="Password"><Input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></Label>
          {needCode && (
            <Label text="Authenticator code">
              <Input inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={code} onChange={(e) => setCode(e.target.value)} autoFocus />
            </Label>
          )}
          {workspaces.length > 0 && (
            <Label text="Workspace">
              <select className="w-full rounded-md border px-3 py-1.5 text-sm dark:bg-zinc-950" value={workspace} onChange={(e) => setWorkspace(e.target.value)}>
                {workspaces.map((w) => <option key={w}>{w}</option>)}
              </select>
            </Label>
          )}
          <ErrorBox error={error} />
          <Button type="submit" disabled={busy} className="w-full">{busy ? "Signing in…" : "Sign in"}</Button>
        </form>
      </Card>
    </div>
  );
}
