"use client";
// "How each part is doing" — health chip per restaurant part, from our DB
// today. When the client's current POS system connects, the backend fills
// this through the same /overview/today feed — UI unchanged.
type Feed = {
  period: string;
  unavailable_metrics: string[];
  source_status?: Record<string, { state: string; recommendations: number | null }>;
  data_provenance?: { notice: string; latest_order_at: string | null };
  revenue: { revenue: number };
  orders: { orders: number };
  kitchen: { avg_prep_min: number };
  stock: { recorded_items?: number; low_stock: { name: string }[] };
  bookings: { covers_today: number };
  staff: { scheduled: number };
};

const PARTS = [
  { key: "revenue", label: "Money" },
  { key: "kitchen", label: "Kitchen" },
  { key: "menu", label: "Menu" },
  { key: "stock", label: "Stock" },
  { key: "bookings", label: "Bookings" },
  { key: "staff", label: "Staff" },
  { key: "purchasing", label: "Purchasing" },
] as const;

export default function PartHealth({ feed }: { feed: Feed }) {
  const health = (key: string): { label: string; tone: "good" | "warn" | "muted" } => {
    switch (key) {
      case "revenue":
        return feed.revenue.revenue
          ? { label: `KSh ${Math.round(feed.revenue.revenue).toLocaleString()} · ${feed.period}`, tone: "good" }
          : { label: "No paid sales recorded in this period", tone: "muted" };
      case "kitchen":
        if (feed.unavailable_metrics.includes("kitchen")) return { label: "Timing data unavailable", tone: "muted" };
        return feed.kitchen.avg_prep_min
          ? { label: `${feed.kitchen.avg_prep_min} min avg prep`, tone: "good" }
          : { label: "Not available", tone: "muted" };
      case "menu":
        return feed.orders.orders
          ? { label: `${feed.orders.orders} orders · ${feed.period}`, tone: "good" }
          : { label: "No orders recorded in this period", tone: "muted" };
      case "stock":
        return feed.stock.low_stock.length
          ? { label: `${feed.stock.low_stock.length} running low`, tone: "warn" }
          : { label: feed.stock.recorded_items ? "No recorded items below threshold" : "No inventory records available", tone: "muted" };
      case "bookings":
        return feed.bookings.covers_today
          ? { label: `${feed.bookings.covers_today} covers · ${feed.period}`, tone: "good" }
          : { label: "No expected covers recorded today", tone: "muted" };
      case "staff":
        return feed.staff.scheduled
          ? { label: `${feed.staff.scheduled} scheduled`, tone: "good" }
          : { label: "Not available", tone: "muted" };
      default:
        return { label: "Not available", tone: "muted" }; // purchasing: waits for POS sync
    }
  };

  return (
    <section>
      <p className="mb-1 text-[10px] font-bold uppercase tracking-[0.16em] text-[var(--v-muted-foreground)]">Recorded restaurant data</p>
        <h2 className="font-display text-2xl font-semibold tracking-[-0.035em]">How each part is doing</h2>
      <p className="text-xs text-[var(--v-muted-foreground)]">{feed.data_provenance?.notice ?? "Source completeness has not been verified."}</p>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4 mt-3">
        {PARTS.map(({ key, label }) => {
          const h = health(key);
          return (
            <div key={key} className="rounded-xl border border-[var(--v-border)] bg-[hsl(42_40%_99_/_0.72)] p-4">
              <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--v-muted-foreground)]">{label}</p>
              <p className={`font-display mt-1.5 text-lg font-semibold tracking-[-0.02em] ${
                h.tone === "warn" ? "text-[var(--v-warn)]" : h.tone === "muted" ? "text-[var(--v-muted-foreground)]" : ""
              }`}>{h.label}</p>
            </div>
          );
        })}
      </div>
      {feed.data_provenance?.latest_order_at && <p className="mt-3 text-xs text-[var(--v-muted-foreground)]">
        Latest recorded order (UTC): {feed.data_provenance.latest_order_at}
      </p>}
      {feed.source_status && <div className="mt-4">
        <h3 className="text-sm font-semibold">Analysis coverage</h3>
        <ul className="mt-2 grid gap-2 text-xs sm:grid-cols-2">
          {Object.entries(feed.source_status).map(([domain, result]) => <li key={domain}>
            <span className="capitalize">{domain.replaceAll("_", " ")}</span>: {result.state === "failed"
              ? "Analysis failed — retry or review source records"
              : result.state === "evaluated"
                ? `${result.recommendations ?? 0} recommendations from recorded data`
                : result.state === "insufficient_data" ? "Not enough recorded data" : "Not evaluated in this feed"}
          </li>)}
        </ul>
      </div>}
    </section>
  );
}