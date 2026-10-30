"use client";

export function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="mb-3 mt-6 text-xs font-bold uppercase tracking-widest text-zinc-400 first:mt-0">{children}</p>
  );
}

export function GlassCard({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <div className={`owner-glass-panel rounded-2xl p-4 ${className}`}>{children}</div>;
}

export function SolidNumberCard({
  title,
  body,
  hint,
}: {
  title: string;
  body: string;
  hint?: string;
}) {
  return (
    <div className="owner-solid-card rounded-2xl p-4 text-white">
      <p className="text-sm text-zinc-300">{title}</p>
      <p className="mt-2 text-2xl font-bold tracking-tight">{body}</p>
      {hint && <p className="mt-2 text-xs text-zinc-400">{hint}</p>}
    </div>
  );
}

export function DayOneChecklist() {
  const items = [
    "Opening stock counted (Waiting)",
    "Suppliers added (Waiting)",
    "Recipes and costs (0 of 0 dishes — add your menu first)",
    "Sales from your till (Waiting on Quick Sell)",
    "First money report (Day 5 after sales connect)",
  ];
  return (
    <ul className="divide-y divide-white/10 text-sm">
      {items.map((line) => (
        <li key={line} className="py-3">
          {line}
        </li>
      ))}
    </ul>
  );
}

export function WaitingNotice({ children }: { children: React.ReactNode }) {
  return <p className="text-sm leading-relaxed text-zinc-300">{children}</p>;
}
