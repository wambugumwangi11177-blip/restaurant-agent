"use client";
// Vibanda Village shell — 3-tab nav (Home/OS/Support). Bottom bar on mobile,
// top tabs on desktop. Only Vibanda-tenant users ever see this tree.
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { Home, MessageCircle, FileText } from "lucide-react";
import { fmtDate } from "@/lib/format";
import { useAuth } from "@/context/AuthContext";
import { isVibanda, VIBANDA_SYNTHETIC_TENANT } from "@/lib/tenantHome";
import { tierHome, type StaffTier } from "@/lib/permissions";
import NotificationBell from "@/components/NotificationBell";

// Three tabs, by the owner's decision (2026-09-19): Home is where the system
// talks to you, OS is where you talk to the system, Reports is the record.
// Support was removed from the nav — the route still exists so any bookmark or
// emailed link keeps resolving, it just isn't a destination we offer.
const TABS = [
  { href: "/vibanda", label: "Home", icon: Home },
  { href: "/vibanda/os", label: "OS", icon: MessageCircle },
  { href: "/vibanda/reports", label: "Reports", icon: FileText },
];

export default function VibandaLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, isLoading } = useAuth();
  const owner = user?.role === "admin" || user?.role === "superadmin";
  const allowed = owner && isVibanda(user?.tenant_name);
  useEffect(() => {
    if (isLoading) return;
    if (!user) router.replace("/login");
    else if (!owner) router.replace(tierHome(user.staff_role as StaffTier | null));
    else if (!allowed) router.replace("/dashboard");
  }, [user, isLoading, owner, allowed, router]);
  if (isLoading || !allowed) {
    return <p role="status" className="p-6">Checking account access…</p>;
  }
  return (
    <div className="vibanda-theme min-h-screen pb-20 md:pb-0">
      <header className="px-4 pt-6 pb-2 md:px-8">
      <div className="float-right"><NotificationBell ownerHome="/vibanda" /></div>
        {/* Sketch: tiny uppercase eyebrow date line */}
        <p className="mb-2 text-[10px] font-bold uppercase tracking-[0.16em] text-[var(--v-muted-foreground)]">{fmtDate()} · Nairobi</p>
        {process.env.NEXT_PUBLIC_SYNTHETIC_DEMO === "true" && user?.tenant_name === VIBANDA_SYNTHETIC_TENANT && (
          <p className="mb-2 inline-flex rounded-full border border-[hsl(43_76%_57_/.45)] bg-[hsl(43_76%_57_/.12)] px-2 py-1 text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--v-muted-foreground)]">Synthetic staging data · not Macsoft</p>
        )}
        <nav className="hidden md:flex gap-1 mt-3">
          {TABS.map(({ href, label, icon: Icon }) => {
            const active = pathname === href;
            return (
              <Link
                key={href}
                href={href}
                className={`flex items-center gap-2 rounded-lg px-3 py-2.5 text-[12px] font-medium ${
                  active
                    ? "bg-[var(--v-primary)] text-[var(--v-primary-foreground)]"
                    : "text-[var(--v-muted-foreground)] hover:bg-[var(--v-muted)] hover:text-[var(--v-foreground)]"
                }`}
              >
                <Icon size={16} /> {label}
              </Link>
            );
          })}
        </nav>
      </header>
      <main className="mx-auto max-w-[1180px] px-4 pb-16 pt-4 sm:px-7 lg:px-10">{children}</main>
      <nav className="fixed bottom-0 inset-x-0 md:hidden bg-[var(--v-card)] border-t border-[var(--v-border)] grid grid-cols-3">
        {TABS.map(({ href, label, icon: Icon }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className={`flex flex-col items-center gap-1 py-3 text-xs ${
                active ? "text-[var(--v-primary)]" : "text-[var(--v-muted-foreground)]"
              }`}
            >
              <Icon size={20} /> {label}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
