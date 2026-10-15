"use client";
import { useEffect, useState } from "react";
import { ChevronDown } from "lucide-react";
import StateChip from "@/components/owner/StateChip";
import { BLOCK_TITLES } from "@/lib/owner/blocks";
import { kes } from "@/lib/owner/format";
import { AREA_KEYS, type Area, type AreaKey, type AreaSummary, type HealthStatus, type OwnerHome } from "@/lib/owner/types";

const DOT: Record<HealthStatus, string> = {
  good: "bg-[var(--v-good)]", watch: "bg-[var(--v-warn)]", bad: "bg-[var(--v-destructive)]", unknown: "bg-[var(--v-border)]",
};

function headline(s: AreaSummary): string {
  if (s.number == null) return "Not set up";
  return s.unit === "KES" ? kes(s.number) : s.unit === "%" ? `${Number(s.number.toFixed(1))}%` : String(s.number);
}

/** The area key a `#area-<key>` link points at, or null. */
export function areaFromHash(hash: string): AreaKey | null {
  const key = hash.replace(/^#area-/, "");
  return (AREA_KEYS as readonly string[]).includes(key) ? (key as AreaKey) : null;
}

/** The six area panels: one line each (one number, one word), opening in place. A link to `#area-<key>` opens that panel. */
export default function AreaPanels({ areas }: { areas: OwnerHome["areas"] }) {
  const [open, setOpen] = useState<Set<AreaKey>>(new Set());

  useEffect(() => {
    const reveal = () => {
      const key = areaFromHash(window.location.hash);
      if (!key) return;
      setOpen((o) => new Set(o).add(key));
      window.requestAnimationFrame(() => document.getElementById(`area-${key}`)?.scrollIntoView?.({ block: "start" }));
    };
    reveal();
    window.addEventListener("hashchange", reveal);
    return () => window.removeEventListener("hashchange", reveal);
  }, []);

  const toggle = (key: AreaKey) => setOpen((o) => { const n = new Set(o); if (n.has(key)) n.delete(key); else n.add(key); return n; });

  return (
    <div className="space-y-2">
      {AREA_KEYS.map((key) => {
        const area = areas[key];
        if (!area) return null;
        const isOpen = open.has(key);
        return (
          <section key={key} id={`area-${key}`} className="scroll-mt-4 rounded-xl border border-[var(--v-border)] bg-[var(--v-card)]">
            <h3>
              <button type="button" aria-expanded={isOpen} aria-controls={`area-${key}-body`} onClick={() => toggle(key)}
                className="flex min-h-14 w-full items-center gap-3 px-4 py-3 text-left">
                <span aria-hidden className={`h-2.5 w-2.5 shrink-0 rounded-full ${DOT[area.summary.status]}`} />
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-bold">{area.title}</span>
                  <span className="block truncate text-[11px] text-[var(--v-muted-foreground)]">{area.summary.word} · {area.summary.label}</span>
                </span>
                <span className="font-display text-lg font-semibold tracking-[-0.03em]">{headline(area.summary)}</span>
                <ChevronDown size={16} aria-hidden className={`shrink-0 transition-transform ${isOpen ? "rotate-180" : ""}`} />
              </button>
            </h3>
            {isOpen && <div id={`area-${key}-body`} role="region" aria-label={area.title} className="space-y-3 border-t border-[var(--v-border)] p-4"><AreaBody area={area} /></div>}
          </section>
        );
      })}
    </div>
  );
}

/** Every block of an area, in the owner's words, with its state. A block without a drawing of its own still says what it is and why it is empty. */
function AreaBody({ area }: { area: Area }) {
  const titles = BLOCK_TITLES[area.key] ?? {};
  return (
    <ul className="space-y-2">
      {Object.entries(area.blocks).map(([key, block]) => (
        <li key={key} className="flex flex-wrap items-center gap-2 text-xs">
          <span className="font-semibold">{titles[key] ?? key.replace(/_/g, " ")}</span>
          <StateChip block={block} />
          {block.reason && <span className="text-[var(--v-muted-foreground)]">{String(block.reason)}</span>}
        </li>
      ))}
    </ul>
  );
}
