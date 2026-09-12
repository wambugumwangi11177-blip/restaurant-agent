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
      <h2 className="text-lg font-semibold">How each part is doing</h2>
      <p className="text-xs text-[var(--muted-foreground)]">Live from your restaurant · POS sync coming soon</p>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mt-3">
        {PARTS.map(({ key, label }) => {
          const h = health(key);
          return (
            <div key={key} className="rounded-2xl border border-[var(--border)] p-4">
              <p className="text-xs text-[var(--muted-foreground)]">{label}</p>
              <p className={`text-sm font-medium mt-1 ${
                h.tone === "warn" ? "text-amber-600" : h.tone === "muted" ? "text-[var(--muted-foreground)]" : ""
              }`}>{h.label}</p>
            </div>
          );
        })}
      </div>
    </section>
  );
}