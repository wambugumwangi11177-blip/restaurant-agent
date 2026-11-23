"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Home, Wallet, Package, Users, MoreHorizontal } from "lucide-react";
import NotificationBell from "@/components/NotificationBell";
import "@/styles/owner-glass.css";

const NAV = [
  { href: "/eleven", label: "Home", icon: Home, match: (p: string) => p === "/eleven" },
  { href: "/eleven/money", label: "Money", icon: Wallet, match: (p: string) => p.startsWith("/eleven/money") },
  { href: "/eleven/stock", label: "Stock", icon: Package, match: (p: string) => p.startsWith("/eleven/stock") },
  { href: "/eleven/team", label: "Team", icon: Users, match: (p: string) => p.startsWith("/eleven/team") || p.startsWith("/eleven/schedule") },
  {
    href: "/eleven/more",
    label: "More",
    icon: MoreHorizontal,
    match: (p: string) =>
      p.startsWith("/eleven/more") ||
      ["/eleven/sales-dishes", "/eleven/cash-check", "/eleven/staff", "/eleven/settings", "/eleven/ask", "/eleven/reports", "/eleven/alerts", "/eleven/approvals", "/eleven/activity", "/eleven/deliveries", "/eleven/import", "/eleven/settings/team-rules"].some(
        (x) => p.startsWith(x),
      ),
  },
] as const;

export default function OwnerShell({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  const pathname = usePathname() ?? "";

  return (
    <div className="owner-glass-theme owner-desktop-nav">
      <header className="owner-glass-panel owner-shell-header flex max-w-3xl items-center justify-between rounded-full px-5 py-3 md:ml-6 md:mr-auto md:w-auto md:max-w-3xl">
        <h1 className="min-w-0 truncate pl-0.5 text-lg text-[var(--text)]">{title}</h1>
        <div className="flex items-center gap-2">
          <NotificationBell ownerHome="/eleven" />
          <Link
            href="/eleven/settings"
            className="flex h-9 w-9 items-center justify-center rounded-full border border-[var(--border)] bg-[var(--accent)] text-xs font-bold text-[var(--bg)]"
            aria-label="Settings"
          >
            E
          </Link>
        </div>
      </header>
      <main className="owner-main-pad mx-auto max-w-3xl px-4 py-4 md:px-6 md:pb-4">{children}</main>

      <nav
        aria-label="Main"
        className="owner-glass-panel owner-nav owner-nav-desktop fixed left-1/2 z-50 flex h-[72px] w-[calc(100%-24px)] max-w-[420px] -translate-x-1/2 items-center justify-around rounded-full px-2 md:left-4 md:h-auto md:w-[88px] md:max-w-none md:translate-x-0 md:flex-col md:gap-2 md:py-4"
      >
        {NAV.map(({ href, label, icon: Icon, match }) => {
          const active = match(pathname);
          return (
            <Link
              key={href}
              href={href}
              className={`flex min-h-11 min-w-[56px] flex-col items-center justify-center gap-0.5 rounded-full text-[10px] font-medium md:min-w-0 md:w-full ${
                active ? "text-[var(--text)]" : "text-zinc-400"
              }`}
            >
              <span
                className={`flex h-10 w-10 items-center justify-center rounded-full ${
                  active ? "nav-pill-active" : ""
                }`}
              >
                <Icon size={22} strokeWidth={1.75} />
              </span>
              <span className="md:hidden">{label}</span>
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
