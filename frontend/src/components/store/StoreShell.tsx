"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { Home, Package, Truck, UserRound } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { homeFor } from "@/lib/tenantHome";
import "@/styles/owner-glass.css";

const NAV = [
  { href: "/store", label: "Home", icon: Home, match: (p: string) => p === "/store" || p.startsWith("/store/questions") },
  { href: "/store/deliveries", label: "In", icon: Truck, match: (p: string) => p.startsWith("/store/deliveries") || p.startsWith("/store/suppliers") },
  { href: "/store/stock", label: "Stock", icon: Package, match: (p: string) => ["/store/stock", "/store/issue", "/store/waste", "/store/close", "/store/chefs"].some((prefix) => p.startsWith(prefix)) },
  { href: "/store/account", label: "Account", icon: UserRound, match: (p: string) => p.startsWith("/store/account") || p.startsWith("/store/costs") || p.startsWith("/store/recipes") },
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
  const allowed = user?.staff_role === "stockkeeper" || user?.role === "admin" || user?.role === "superadmin";

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
    <div className="owner-glass-theme pb-28">
      <header className="owner-glass-panel mx-auto mt-3 flex max-w-md items-center justify-between rounded-full px-4 py-2.5">
        <div>
          <p className="text-[10px] uppercase tracking-[0.16em] text-zinc-400">LEVIII Store</p>
          <h1 className="text-base font-semibold">{title}</h1>
        </div>
      </header>
      <main className="mx-auto max-w-md px-4 py-4">{children}</main>
      <nav
        aria-label="Store"
        className="owner-glass-panel fixed bottom-3 left-1/2 z-50 flex h-[72px] w-[calc(100%-24px)] max-w-[420px] -translate-x-1/2 items-center justify-around rounded-full px-2"
      >
        {NAV.map(({ href, label, icon: Icon, match }) => {
          const active = match(pathname);
          return (
            <Link
              key={href}
              href={href}
              className={`flex min-h-11 min-w-[64px] flex-col items-center justify-center gap-0.5 rounded-full text-[10px] font-semibold ${
                active ? "text-black" : "text-zinc-400"
              }`}
            >
              <span className={`flex h-10 w-10 items-center justify-center rounded-full ${active ? "bg-white/95 text-black shadow-lg" : ""}`}>
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
