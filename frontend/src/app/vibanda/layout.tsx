"use client";
// Vibanda Village shell — 3-tab nav (Home/OS/Reports). Bottom bar on mobile,
// top tabs on desktop.
//
// OWNER-ONLY, and it guards for it. Every page in this tree reads
// GET /overview/today or GET /reports, both gated to ADMIN by the backend
// (auth.py's require_staff_role with an empty allow-set). A staff member who
// reached here got a 403 on every call and a generic error screen with no way
// out — app/staff/layout.tsx sent them to /dashboard and
// app/dashboard/layout.tsx sent them straight back. Sending them to their own
// tier home is the fix; guarding here as well is the belt to that brace, so a
// direct link cannot reproduce it.
import { useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Home, MessageCircle, FileText } from "lucide-react";
import { fmtDate } from "@/lib/format";
import { useAuth } from "@/context/AuthContext";
import { tierHome, type StaffTier } from "@/lib/permissions";

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
  const isStaffAccount = (user?.role ?? "").toLowerCase() === "staff";
  const staffRole = (user?.staff_role ?? null) as StaffTier | null;

  useEffect(() => {
    if (isLoading) return;
    if (!user) {
      router.replace("/login");
      return;
    }
    if (isStaffAccount) {
      // Their own pages work. This one cannot, for them.
      router.replace(staffRole ? tierHome(staffRole) : "/dashboard");
    }
  }, [user, isLoading, isStaffAccount, staffRole, router]);

  if (isLoading || !user || isStaffAccount) {
    return (
      <div className="vibanda-theme flex min-h-screen items-center justify-center">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-[var(--v-primary)] border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="vibanda-theme min-h-screen pb-20 md:pb-0">
      <header className="px-4 pt-6 pb-2 md:px-8">
        {/* Sketch: tiny uppercase eyebrow date line */}
        <p className="mb-2 text-[10px] font-bold uppercase tracking-[0.16em] text-[var(--v-muted-foreground)]">{fmtDate()} · Nairobi</p>
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