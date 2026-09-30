"use client";
// Demo Restaurant shell — a clone of the Vibanda Village shell (Home/OS/Reports).
// Bottom bar on mobile, top tabs on desktop. Only the Demo Restaurant tenant
// ever sees this tree. Unlike Vibanda it records its data directly, so nothing
// here waits on MacSoft or any external data push.
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { Home, MessageCircle, FileText } from "lucide-react";
import { fmtDate } from "@/lib/format";
import { useAuth } from "@/context/AuthContext";
import { isDemoRestaurant } from "@/lib/tenantHome";
import { tierHome, type StaffTier } from "@/lib/permissions";

const TABS = [
  { href: "/demo", label: "Home", icon: Home },
  { href: "/demo/os", label: "OS", icon: MessageCircle },
  { href: "/demo/reports", label: "Reports", icon: FileText },
];

export default function DemoLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, isLoading } = useAuth();
  const owner = user?.role === "admin" || user?.role === "superadmin";
  const allowed = owner && isDemoRestaurant(user?.tenant_name);
  useEffect(() => {
    if (isLoading) return;
    if (!user) router.replace("/login");
    else if (!owner)
      router.replace(tierHome(user.staff_role as StaffTier | null));
    else if (!allowed) router.replace("/dashboard");
  }, [user, isLoading, owner, allowed, router]);
  if (isLoading || !allowed) {
    return (
      <p role="status" className="p-6">
        Checking account access…
      </p>
    );
  }
  return (
    <div className="vibanda-theme min-h-screen pb-20 md:pb-0">
      <header className="px-4 pt-6 pb-2 md:px-8">
        {/* Sketch: tiny uppercase eyebrow date line */}
        <p className="mb-2 text-[10px] font-bold uppercase tracking-[0.16em] text-[var(--v-muted-foreground)]">
          {fmtDate()} · Nairobi
        </p>
        <nav className="hidden md:flex gap-1 mt-3 print:hidden">
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
      <main className="mx-auto max-w-[1180px] px-4 pb-16 pt-4 sm:px-7 lg:px-10">
        <p className="mb-6 rounded-lg border border-[var(--v-border)] bg-[var(--v-card)] px-4 py-3 text-xs text-[var(--v-muted-foreground)]">
          Demo Restaurant · Illustrative sample data. Calculated opportunities
          and forecasts, not actual results. Demo actions do not change business
          records.
        </p>
        {children}
      </main>
      <nav className="fixed bottom-0 inset-x-0 md:hidden print:hidden bg-[var(--v-card)] border-t border-[var(--v-border)] grid grid-cols-3">
        {TABS.map(({ href, label, icon: Icon }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className={`flex flex-col items-center gap-1 py-3 text-xs ${
                active
                  ? "text-[var(--v-primary)]"
                  : "text-[var(--v-muted-foreground)]"
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
