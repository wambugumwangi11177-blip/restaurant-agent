"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Home, Wallet, Package, MessageCircle, MoreHorizontal } from "lucide-react";
import NotificationBell from "@/components/NotificationBell";
import "@/styles/owner-glass.css";

const NAV = [
  { href: "/eleven", label: "Home", icon: Home, match: (p: string) => p === "/eleven" },
  { href: "/eleven/money", label: "Money", icon: Wallet, match: (p: string) => p.startsWith("/eleven/money") },
  { href: "/eleven/stock", label: "Stock", icon: Package, match: (p: string) => p.startsWith("/eleven/stock") },
  { href: "/eleven/ask", label: "Ask", icon: MessageCircle, match: (p: string) => p.startsWith("/eleven/ask") },
  {
    href: "/eleven/more",
    label: "More",
    icon: MoreHorizontal,
    match: (p: string) =>
      p.startsWith("/eleven/more") ||
      ["/eleven/sales-dishes", "/eleven/cash-check", "/eleven/staff", "/eleven/settings", "/eleven/reports", "/eleven/alerts"].some(
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
    <div className="owner-glass-theme pb-24 md:pl-[104px] md:pb-8">
      <header className="owner-glass-panel mx-auto mt-3 flex max-w-3xl items-center justify-between rounded-full px-4 py-2.5 md:ml-6 md:mr-auto">
        <h1 className="text-base font-semibold tracking-wide">{title}</h1>
        <div className="flex items-center gap-2">
          <NotificationBell ownerHome="/eleven" />
          <Link
            href="/eleven/settings"
            className="flex h-9 w-9 items-center justify-center rounded-full border border-white/20 bg-white/90 text-xs font-bold text-black"
            aria-label="Settings"
          >
            E
          </Link>
        </div>
      </header>
      <main className="mx-auto max-w-3xl px-4 py-4 md:px-6">{children}</main>

      <nav
        aria-label="Main"
        className="owner-glass-panel fixed bottom-3 left-1/2 z-50 flex h-[72px] w-[calc(100%-24px)] max-w-[420px] -translate-x-1/2 items-center justify-around rounded-full px-2 md:bottom-auto md:left-4 md:top-6 md:h-auto md:w-[88px] md:max-w-none md:translate-x-0 md:flex-col md:gap-2 md:py-4"
      >
        {NAV.map(({ href, label, icon: Icon, match }) => {
          const active = match(pathname);
          return (
            <Link
              key={href}
              href={href}
              className={`flex min-h-11 min-w-[56px] flex-col items-center justify-center gap-0.5 rounded-full text-[10px] font-semibold md:min-w-0 md:w-full ${
                active ? "text-black" : "text-zinc-400"
              }`}
            >
              <span
                className={`flex h-10 w-10 items-center justify-center rounded-full ${
                  active ? "bg-white/95 text-black shadow-lg" : ""
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
