import type { ReactNode } from "react";
import type { OwnerHome } from "@/lib/owner/types";
import { kes } from "@/lib/owner/format";

type Node = { title: string; detail: string };

function Map({ label, nodes }: { label: string; nodes: Node[] }) {
  if (nodes.length === 0) return <p className="text-xs text-[var(--v-muted-foreground)]">This picture fills in once the restaurant has records to show.</p>;
  return (
    <ol className="grid gap-2 sm:grid-cols-2" aria-label={label}>
      {nodes.map((n, i) => (
        <li key={n.title} className="rounded-lg border border-[var(--v-border)] bg-[var(--v-card)] p-3">
          <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--v-muted-foreground)]">{i + 1}</p>
          <p className="mt-1 text-sm font-semibold">{n.title}</p>
          <p className="mt-0.5 text-[11px] leading-relaxed text-[var(--v-muted-foreground)]">{n.detail}</p>
        </li>
      ))}
    </ol>
  );
}

function Block({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section id={id} className="scroll-mt-4 rounded-xl border border-[var(--v-border)] bg-[var(--v-bg)] p-4">
      <h3 className="font-display text-lg font-semibold tracking-[-0.02em]">{title}</h3>
      <div className="mt-3">{children}</div>
    </section>
  );
}

/** The guide's pictures, drawn from the same Home payload as the panels above. */
export default function HowItWorks({ home }: { home: OwnerHome }) {
  const sales = home.pulse?.sales_today;
  const areas = home.areas;
  const money = areas?.money?.blocks as Record<string, { state?: string; lines?: { key: string; kes: number }[]; food_cost_pct?: number; wages_pct?: number | null; prime_cost_pct?: number | null }> | undefined;
  const kept = money?.pnl?.lines?.find((l) => l.key === "kept")?.kes;
  const dishes = (areas?.sales_dishes?.blocks?.matrix as { dishes?: { name: string }[] } | undefined)?.dishes?.length;
  const trust = areas?.permits?.blocks?.data_trust as { costs_known_pct?: number; dishes?: number; to_fix?: number } | undefined;
  const health = home.health?.tiles ?? [];
  return (
    <div className="space-y-4">
      <Block id="fig-a" title="How the restaurant connects">
        <Map label="System map" nodes={[
          { title: "Sales", detail: sales == null ? "Today's sales appear here once an order is paid." : `${kes(sales)} paid in the open service day.` },
          { title: "Dishes", detail: dishes == null ? "Each dish's cost and price land here." : `${dishes} dishes on the map of what sells and what earns.` },
          { title: "Store", detail: areas?.store?.summary?.word ? `Store: ${areas.store.summary.word}.` : "Counts, handovers and reorders." },
          { title: "Cash", detail: areas?.cash?.summary?.word ? `Cash check: ${areas.cash.summary.word}.` : "The drawer, M-Pesa and the menu price." },
          { title: "Staff", detail: areas?.staff?.summary?.word ? `Team: ${areas.staff.summary.word}.` : "Hours and wages against sales." },
          { title: "Permits", detail: areas?.permits?.summary?.word ? `Licences and targets: ${areas.permits.summary.word}.` : "Licences and the targets you set." },
        ]} />
      </Block>
      <Block id="fig-b" title="Follow a shilling">
        <Map label="Follow a shilling" nodes={[
          { title: "A guest pays", detail: sales == null ? "Waiting for a paid order." : `${kes(sales)} came in today.` },
          { title: "Ingredients take their share", detail: money?.cost_dials?.food_cost_pct != null ? `${money.cost_dials.food_cost_pct}% of sales.` : "Enter dish costs to see this share." },
          { title: "Wages take theirs", detail: money?.cost_dials?.wages_pct != null ? `${money.cost_dials.wages_pct}% of sales.` : "Wages show once hours are logged." },
          { title: "What you kept", detail: kept == null ? "The month's kept figure shows once costs are entered." : `${kes(kept)} kept in this month's picture.` },
        ]} />
      </Block>
      <Block id="fig-1" title="What can go wrong, and what catches it">
        <Map label="Doors and the checks" nodes={[
          { title: "The till", detail: "A short count, a cancelled sale, or a price under the menu." },
          { title: "M-Pesa", detail: "A sale with no payment on the statement, or a payment with no sale." },
          { title: "The store", detail: "Stock used beyond the recipes, or a handover the kitchen did not confirm." },
          { title: "The calendar", detail: "A licence about to run out, or a bill the next 30 days cannot cover." },
        ]} />
      </Block>
      <Block id="fig-5" title="How a price is decided">
        <Map label="Price decision" nodes={[
          { title: "Know the cost", detail: trust?.to_fix ? `${trust.to_fix} dishes still have no ingredient cost.` : trust?.costs_known_pct != null ? `${trust.costs_known_pct}% of dishes have a cost.` : "Dish costs make the price honest." },
          { title: "Keep your floor", detail: "The suggested price is the lowest step that keeps the share you set." },
          { title: "Watch what happened", detail: "After 14 days, the menu review says whether sales moved." },
          { title: "You decide", detail: "Nothing changes on the menu until you approve it." },
        ]} />
      </Block>
      <Block id="fig-9" title="The screens, the week, and the team">
        <Map label="Screens and team" nodes={[
          { title: "Home", detail: "Today, the last 7 days, or the last 30 days — the same paid sales everywhere." },
          { title: "Questions", detail: "Questions in your words. The numbers stay the ones already on Home." },
          { title: "Reports", detail: "The day, the week, the month and the year, from the same books." },
          { title: "Health", detail: health.length ? health.map((t) => t.title).join(" · ") : "Six tiles, one for each part of the restaurant." },
          { title: "Your team", detail: "Owner, manager, supervisor, accountant, storekeeper, kitchen, waiter. Each sees their own work." },
          { title: "Alerts", detail: "A licence, a bill, a count or a price — the loudest thing is the one that costs money now." },
        ]} />
      </Block>
    </div>
  );
}
