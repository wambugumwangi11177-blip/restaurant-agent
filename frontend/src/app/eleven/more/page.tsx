"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import OwnerShell from "@/components/eleven/OwnerShell";
import { posHasLiveData } from "@/lib/posLive";

const CORE_LINKS = [
  { href: "/eleven/team", title: "Team", desc: "Who is on shift, PINs, handovers, Jack setup answers" },
  { href: "/eleven/staff", title: "Staff", desc: "Logins and setup progress" },
  { href: "/eleven/import", title: "Import", desc: "Bring in items, suppliers, recipes, and an opening count" },
  { href: "/eleven/deliveries", title: "Deliveries", desc: "Photos, mismatches, and invoice prices" },
  { href: "/eleven/handovers", title: "Handovers", desc: "Store to kitchen with photos" },
  { href: "/eleven/approvals", title: "Approvals", desc: "What is waiting, and what you already decided" },
  { href: "/eleven/activity", title: "Activity", desc: "The day, by person and type" },
  { href: "/eleven/settings", title: "Permits & Settings", desc: "Licences and your thresholds" },
  { href: "/eleven/reports", title: "Reports", desc: "Store activity summaries" },
  { href: "/eleven/alerts", title: "Alerts", desc: "What needs you now" },
] as const;

const POS_LINKS = [
  { href: "/eleven/sales-dishes", title: "Sales & Dishes", desc: "From parsed POS receipts" },
  { href: "/eleven/cash-check", title: "Cash Check", desc: "Till and receipt matching" },
] as const;

export default function ElevenMorePage() {
  const [posLive, setPosLive] = useState(false);
  useEffect(() => {
    posHasLiveData().then(setPosLive).catch(() => setPosLive(false));
  }, []);
  const links = posLive ? [...POS_LINKS, ...CORE_LINKS] : CORE_LINKS;

  return (
    <OwnerShell title="More">
      <nav className="space-y-3">
        {links.map(({ href, title, desc }) => (
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
      {!posLive && (
        <p className="mt-4 text-xs text-zinc-500">
          Sales, dishes, and cash check stay hidden until the POS webhook delivers receipts.
        </p>
      )}
    </OwnerShell>
  );
}