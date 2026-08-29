"use client";

import dynamic from "next/dynamic";
import type { ComponentType } from "react";

export interface FullModule {
    title: string;
    subtitle: string;
    Component: ComponentType;
}

const withLoader = (load: () => Promise<{ default: ComponentType }>) => {
    const C = dynamic(load, { ssr: false, loading: () => <div className="bg-surface rounded-xl h-40 animate-pulse" /> });
    return C;
};

// One slug per module — the hub sections link here via ModuleShell's fullHref.
export const FULL_MODULES: Record<string, FullModule> = {
    pricing: {
        title: "Pricing Intelligence",
        subtitle: "Every reprice / surge / stimulate recommendation, delivery gap, and per-item analysis.",
        Component: withLoader(() => import("./PricingFull")),
    },
    profit: {
        title: "Profit Intelligence",
        subtitle: "Full contribution margins, leaks, dayparts, channels, customer intelligence and forecast.",
        Component: withLoader(() => import("./ProfitFull")),
    },
    menu: {
        title: "Menu Engineering",
        subtitle: "Every dish classified by popularity × profit, with categories, Pareto and trends.",
        Component: withLoader(() => import("./MenuFull")),
    },
    revenue: {
        title: "Revenue Forecast",
        subtitle: "Forecasts, trends, hourly & weekly patterns, segments, and anomalies.",
        Component: withLoader(() => import("./RevenueFull")),
    },
    inventory: {
        title: "Inventory Forecast",
        subtitle: "Every stock item with depletion prediction, velocity, trends and alerts.",
        Component: withLoader(() => import("./InventoryFull")),
    },
    labor: {
        title: "Labor Optimization",
        subtitle: "Daily labor cost vs revenue and every staff member's productivity.",
        Component: withLoader(() => import("./LaborFull")),
    },
    suppliers: {
        title: "Supplier Intelligence",
        subtitle: "Reliability, lead-time variance and price trends for every supplier.",
        Component: withLoader(() => import("./SuppliersFull")),
    },
    kitchen: {
        title: "Kitchen Intelligence",
        subtitle: "Station performance, per-item prep times, rush load and recommendations.",
        Component: withLoader(() => import("./KitchenFull")),
    },
    reservations: {
        title: "Reservation Intelligence",
        subtitle: "No-show analysis, table utilization, RevPASH and overbooking strategy.",
        Component: withLoader(() => import("./ReservationsFull")),
    },
    decisions: {
        title: "Decision Intelligence",
        subtitle: "Every agent's recommendations ranked into one prioritised stream.",
        Component: withLoader(() => import("./DecisionsFull")),
    },
    fraud: {
        title: "Fraud Watch",
        subtitle: "Full suspicious-transaction report — voids, refunds, payment mismatches, off-hours.",
        Component: withLoader(() => import("./FraudFull")),
    },
};
