"use client";
import { useEffect, useState } from "react";
import { ChevronDown, Lock } from "lucide-react";
import AreaBody from "@/components/owner/AreaBody";
import { kes } from "@/lib/owner/format";
import { AREA_KEYS, type AreaKey, type AreaSummary, type HealthStatus, type OwnerHome } from "@/lib/owner/types";

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
export default function AreaPanels({ areas, opensOn = {} }: {
  areas: OwnerHome["areas"];
  /** Panels that are still shut in the guided first week, each with the day it opens. */
  opensOn?: Partial<Record<AreaKey, number>>;
}) {
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
    <div className="leviii-area-list space-y-3">
      {AREA_KEYS.map((key) => {
        const area = areas[key];
        if (!area) return null;
        const shut = opensOn[key];
        const isOpen = open.has(key) && shut == null;
        if (shut != null) {
          return (
            <section key={key} id={`area-${key}`} aria-label={`${area.title}, opens on day ${shut}`} className="rounded-xl border border-dashed border-[var(--v-border)] bg-[var(--v-muted)]">
              <div className="flex min-h-14 items-center gap-3 px-4 py-3 text-[var(--v-muted-foreground)]">
                <Lock size={14} aria-hidden className="shrink-0" />
                <span className="min-w-0 flex-1"><span className="block text-sm font-bold">{area.title}</span><span className="block text-[11px]">Opens on day {shut} of your first week</span></span>
              </div>
            </section>
          );
        }
        return (
          <section key={key} id={`area-${key}`} className="scroll-mt-4 rounded-xl border border-[var(--v-border)] bg-[var(--v-card)]">
            <h3>
              <button type="button" aria-expanded={isOpen} aria-controls={`area-${key}-body`} onClick={() => toggle(key)}
                className="flex min-h-14 w-full items-center gap-3 px-4 py-3 text-left">
                <span aria-hidden className={`h-2.5 w-2.5 shrink-0 rounded-full ${DOT[area.summary.status]}`} />
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-bold">{area.title}</span>
                  <span className="block truncate text-[11px] text-[var(--v-muted-foreground)]">{area.summary.number == null ? area.summary.label : `${area.summary.word} · ${area.summary.label}`}</span>
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
