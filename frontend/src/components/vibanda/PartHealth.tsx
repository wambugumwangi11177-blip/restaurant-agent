"use client";
// "How each part is doing" — health chip per restaurant part, from our DB
// today. When the client's current POS system connects, the backend fills
// this through the same /overview/today feed — UI unchanged.
import { useEffect, useState } from "react";
import api from "@/lib/api";

type Feed = {
  revenue: { revenue: number };
  orders: { orders: number };
  kitchen: { avg_prep_min: number };
  stock: { low_stock: { name: string }[] };
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

export default function PartHealth() {
  const [feed, setFeed] = useState<Feed | null>(null);
  useEffect(() => {
    api.get<Feed>("/api/v1/overview/today").then((r) => setFeed(r.data)).catch(() => {});
  }, []);
  if (!feed) return null;

  const health = (key: string): { label: string; tone: "good" | "warn" | "muted" } => {
    switch (key) {
      case "revenue":
        return feed.revenue.revenue
          ? { label: `KSh ${Math.round(feed.revenue.revenue).toLocaleString()} today`, tone: "good" }
          : { label: "No sales yet today", tone: "muted" };
      case "kitchen":
        return feed.kitchen.avg_prep_min
          ? { label: `${feed.kitchen.avg_prep_min} min avg prep`, tone: "good" }
          : { label: "—", tone: "muted" };
      case "menu":
        return feed.orders.orders
          ? { label: `${feed.orders.orders} orders today`, tone: "good" }
          : { label: "No orders yet", tone: "muted" };
      case "stock":
        return feed.stock.low_stock.length
          ? { label: `${feed.stock.low_stock.length} running low`, tone: "warn" }
          : { label: "Healthy", tone: "good" };
      case "bookings":
        return feed.bookings.covers_today
          ? { label: `${feed.bookings.covers_today} covers today`, tone: "good" }
          : { label: "No bookings yet", tone: "muted" };
      case "staff":
        return feed.staff.scheduled
          ? { label: `${feed.staff.scheduled} scheduled`, tone: "good" }
          : { label: "—", tone: "muted" };
      default:
        return { label: "—", tone: "muted" }; // purchasing: waits for POS sync
    }
  };

  return (
    <section>
      <p className="mb-1 text-[10px] font-bold uppercase tracking-[0.16em] text-[var(--v-muted-foreground)]">Connected restaurant</p>
        <h2 className="font-display text-2xl font-semibold tracking-[-0.035em]">How each part is doing</h2>
      <p className="text-xs text-[var(--v-muted-foreground)]">Live from your restaurant · POS sync coming soon</p>
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
    </section>
  );
}