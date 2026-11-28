"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { Home, Package, Truck, UserRound, Users } from "lucide-react";
import NotificationBell from "@/components/NotificationBell";
import { useAuth } from "@/context/AuthContext";
import api from "@/lib/api";
import { installErrorCapture } from "@/lib/clientErrors";
import { homeFor } from "@/lib/tenantHome";
import "@/styles/owner-glass.css";

const NAV = [
  { href: "/store", label: "Shift", icon: Home, match: (p: string) => p === "/store" || p.startsWith("/store/questions") },
  { href: "/store/deliveries", label: "In", icon: Truck, match: (p: string) => p.startsWith("/store/deliveries") || p.startsWith("/store/suppliers") || p.startsWith("/store/invoice-prices") },
  { href: "/store/stock", label: "Stock", icon: Package, match: (p: string) => ["/store/stock", "/store/issue", "/store/waste", "/store/close", "/store/cash-close", "/store/chefs", "/store/restock", "/store/prep"].some((prefix) => p.startsWith(prefix)) },
  { href: "/store/team", label: "Team", icon: Users, match: (p: string) => p.startsWith("/store/team") || p.startsWith("/store/schedule") },
  {
    href: "/store/account",
    label: "Me",
    icon: UserRound,
    match: (p: string) =>
      p.startsWith("/store/account") ||
      p.startsWith("/store/costs") ||
      p.startsWith("/store/recipes") ||
      p.startsWith("/store/requests") ||
      p.startsWith("/store/invoice-prices"),
  },
] as const;

export default function StoreShell({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  const pathname = usePathname() ?? "";
  const router = useRouter();
  const { user, isLoading } = useAuth();
  const allowed =
    user?.staff_role === "stockkeeper" ||
    user?.staff_role === "controller" ||
    user?.staff_role === "manager" ||
    user?.role === "admin" ||
    user?.role === "superadmin";

  useEffect(
    () => installErrorCapture((report) => api.post("/api/v1/client-errors", report, { skipErrorReport: true })),
    [],
  );

  useEffect(() => {
    const link = document.querySelector<HTMLLinkElement>('link[rel="manifest"]');
    if (link) link.href = "/store-manifest.json";
    let apple = document.querySelector<HTMLMetaElement>('meta[name="apple-mobile-web-app-title"]');
    if (!apple) {
      apple = document.createElement("meta");
      apple.name = "apple-mobile-web-app-title";
      document.head.appendChild(apple);
    }
    apple.content = "LEVIII Store";
  }, []);

  useEffect(() => {
    if (isLoading) return;
    if (!user) router.replace("/login");
    else if (!allowed) router.replace(homeFor(user.tenant_name, user.staff_role));
  }, [user, isLoading, allowed, router]);

  if (isLoading || !allowed) {
    return (
      <p role="status" className="owner-glass-theme p-6 text-zinc-300">
        Checking account access…
      </p>
    );
  }

  return (
    <div className="owner-glass-theme">
      <header className="owner-glass-panel owner-shell-header flex items-center justify-between gap-3 rounded-full px-5 py-3">
        <div className="min-w-0 flex-1 pl-0.5">
          <p className="text-[10px] uppercase tracking-[0.16em] text-zinc-400">LEVIII Store</p>
          <h1 className="truncate text-lg text-[var(--text)]">{title}</h1>
        </div>
        <NotificationBell />
      </header>
      <main className="owner-main-pad mx-auto max-w-md px-4 py-4">{children}</main>
      <nav
        aria-label="Store"
        className="owner-glass-panel owner-nav fixed left-1/2 z-50 flex h-[72px] w-[calc(100%-24px)] max-w-[420px] -translate-x-1/2 items-center justify-around rounded-full px-2"
      >
        {NAV.map(({ href, label, icon: Icon, match }) => {
          const active = match(pathname);
          return (
            <Link
              key={href}
              href={href}
              className={`flex min-h-11 min-w-[64px] flex-col items-center justify-center gap-0.5 rounded-full text-[10px] font-medium ${
                active ? "text-[var(--text)]" : "text-zinc-400"
              }`}
            >
              <span className={`flex h-10 w-10 items-center justify-center rounded-full ${active ? "nav-pill-active" : ""}`}>
                <Icon size={20} strokeWidth={1.75} />
              </span>
              {label}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
