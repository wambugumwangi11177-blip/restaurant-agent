"use client";
// Restaurant OS shell — 4-tab nav. Bottom bar on mobile (thumb-reachable),
// top tabs on desktop. Every page under /dashboard/os inherits this.
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Home, MessageCircle, FileText, LifeBuoy } from "lucide-react";
import { fmtDate } from "@/lib/format";

const TABS = [
  { href: "/dashboard/os", label: "Home", icon: Home },
  { href: "/dashboard/os/chat", label: "OS", icon: MessageCircle },
  { href: "/dashboard/os/reports", label: "Reports", icon: FileText },
  { href: "/dashboard/os/support", label: "Support", icon: LifeBuoy },
];

export default function OsLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="min-h-screen pb-20 md:pb-0">
      <header className="px-4 pt-6 pb-2 md:px-8">
        <p className="text-xs text-[var(--muted-foreground)]">{fmtDate()} · Nairobi</p>
        <nav className="hidden md:flex gap-1 mt-3">
          {TABS.map(({ href, label, icon: Icon }) => {
            const active = pathname === href;
            return (
              <Link
                key={href}
                href={href}
                className={`flex items-center gap-2 rounded-full px-4 py-2 text-sm ${
                  active
                    ? "bg-[var(--accent)] text-white"
                    : "text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                }`}
              >
                <Icon size={16} /> {label}
              </Link>
            );
          })}
        </nav>
      </header>
      <main className="px-4 md:px-8 py-4">{children}</main>
      {/* Mobile: bottom tab bar */}
      <nav className="fixed bottom-0 inset-x-0 md:hidden bg-[var(--card)] border-t border-[var(--border)] grid grid-cols-4">
        {TABS.map(({ href, label, icon: Icon }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className={`flex flex-col items-center gap-1 py-3 text-xs ${
                active ? "text-[var(--accent)]" : "text-[var(--muted-foreground)]"
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