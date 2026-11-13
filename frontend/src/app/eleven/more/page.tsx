"use client";

import Link from "next/link";
import OwnerShell from "@/components/eleven/OwnerShell";

const LINKS = [
  { href: "/eleven/sales-dishes", title: "Sales & Dishes", desc: "Best sellers, price ideas, and hours" },
  { href: "/eleven/cash-check", title: "Cash Check", desc: "Till, cash, and M-Pesa match" },
  { href: "/eleven/staff", title: "Staff", desc: "Logins and setup progress" },
  { href: "/eleven/import", title: "Import", desc: "Bring in items, suppliers, recipes, and an opening count" },
  { href: "/eleven/deliveries", title: "Deliveries", desc: "Photos, AI mismatches, and invoice prices" },
  { href: "/eleven/approvals", title: "Approvals", desc: "What is waiting, and what you already decided" },
  { href: "/eleven/activity", title: "Activity", desc: "The day, by person and type" },
  { href: "/eleven/settings", title: "Permits & Settings", desc: "Licences and your thresholds" },
  { href: "/eleven/reports", title: "Reports", desc: "Close, week, month, and year" },
  { href: "/eleven/alerts", title: "Alerts", desc: "What needs you now" },
];

export default function ElevenMorePage() {
  return (
    <OwnerShell title="More">
      <nav className="space-y-3">
        {LINKS.map(({ href, title, desc }) => (
          <Link
            key={href}
            href={href}
            className="owner-glass-panel flex gap-4 rounded-2xl p-4 transition hover:border-white/25"
          >
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-white/20 text-sm">
              →
            </span>
            <span>
              <strong className="block">{title}</strong>
              <span className="text-xs text-zinc-400">{desc}</span>
            </span>
          </Link>
        ))}
      </nav>
    </OwnerShell>
  );
}
