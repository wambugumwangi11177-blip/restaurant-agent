"use client";
// Vibanda Village shell — 3-tab nav (Home/OS/Support). Bottom bar on mobile,
// top tabs on desktop. Only Vibanda-tenant users ever see this tree.
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Home, MessageCircle, LifeBuoy } from "lucide-react";
import { fmtDate } from "@/lib/format";

const TABS = [
  { href: "/vibanda", label: "Home", icon: Home },
  { href: "/vibanda/os", label: "OS", icon: MessageCircle },
  { href: "/vibanda/support", label: "Support", icon: LifeBuoy },
];

export default function VibandaLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
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