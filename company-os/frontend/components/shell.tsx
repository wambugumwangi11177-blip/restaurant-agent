"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api } from "@/lib/api";

export type Me = {
  user: { id: number; email: string; full_name: string; phone: string | null; mfa_enabled: boolean };
  workspace: { id: number; slug: string; name: string; timezone: string; currency: string };
  role: string;
  permissions: string[];
};

const MeContext = createContext<Me | null>(null);

export function useMe(): Me {
  const me = useContext(MeContext);
  if (!me) throw new Error("useMe outside the app shell");
  return me;
}

export const can = (me: Me, permission: string) => me.permissions.includes(permission);

const NAV: { href: string; label: string; permission?: string }[] = [
  { href: "/", label: "Home" },
  { href: "/approvals", label: "Approvals", permission: "approvals.read" },
  { href: "/records", label: "Records", permission: "records.read" },
  { href: "/memory", label: "Memory", permission: "memory.search" },
  { href: "/agents", label: "Agents", permission: "agents.run" },
  { href: "/audit", label: "Audit", permission: "audit.read" },
  { href: "/settings", label: "Settings" },
];

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [failed, setFailed] = useState(false);
  const isLogin = pathname === "/login";

  useEffect(() => {
    if (isLogin) return;
    api<Me>("auth/me").then(setMe).catch(() => setFailed(true));
  }, [isLogin]);

  if (isLogin) return <>{children}</>;
  if (!me) {
    return <div className="p-8 text-sm text-zinc-500">{failed ? "Could not load your session." : "Loading…"}</div>;
  }

  async function logout() {
    await fetch("/api/session", { method: "DELETE" });
    router.push("/login");
  }

  return (
    <MeContext.Provider value={me}>
      <div className="flex min-h-screen flex-col md:flex-row">
        <aside className="border-b border-zinc-200 bg-white px-4 py-3 md:w-56 md:border-b-0 md:border-r dark:border-zinc-800 dark:bg-zinc-900">
          <div className="mb-3 text-sm font-semibold">{me.workspace.name}</div>
          <nav className="flex gap-1 overflow-x-auto md:flex-col">
            {NAV.filter((n) => !n.permission || can(me, n.permission)).map((n) => {
              const active = n.href === "/" ? pathname === "/" : pathname.startsWith(n.href);
              return (
                <Link
                  key={n.href}
                  href={n.href}
                  className={`whitespace-nowrap rounded-md px-2 py-1.5 text-sm ${active ? "bg-zinc-100 font-medium dark:bg-zinc-800" : "text-zinc-600 hover:bg-zinc-50 dark:text-zinc-400 dark:hover:bg-zinc-800"}`}
                >
                  {n.label}
                </Link>
              );
            })}
          </nav>
          <div className="mt-4 hidden text-xs text-zinc-500 md:block">
            {me.user.full_name} · {me.role}
            <button onClick={logout} className="mt-1 block underline">Sign out</button>
          </div>
        </aside>
        <main className="min-w-0 flex-1 px-4 py-6 md:px-8">{children}</main>
      </div>
    </MeContext.Provider>
  );
}
