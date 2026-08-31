/**
 * overview/actions.ts — map an attention item to a concrete next step.
 *
 * The critique: an alert that only says "something is wrong" is noise; the
 * owner wants "do this". Every item in the Needs-Attention hero gets a real
 * destination that already exists in the app.
 */
import type { AttentionItem } from "./taxonomy";

export interface AttentionAction {
    label: string;
    href: string;
}

export function actionFor(item: AttentionItem): AttentionAction {
    const title = item.title.toLowerCase();
    const source = item.source || "";

    // Inventory / stock signals → go reorder.
    if (source === "inventory" || title.includes("stock-out") || title.includes("stock") || title.includes("run out")) {
        return { label: "Reorder", href: "/dashboard/inventory" };
    }

    // Kitchen throughput / bottlenecks → investigate the KDS.
    if (source === "kitchen" || title.includes("kitchen") || title.includes("bottleneck") || title.includes("prep")) {
        return { label: "Investigate", href: "/dashboard/kitchen" };
    }

    // Menu engineering signals → review the menu module.
    if (source === "menu" || title.includes("menu") || title.includes("high-margin") || title.includes("dead weight")) {
        return { label: "Review", href: "/dashboard/ai/menu" };
    }

    // Bookings / no-show signals → the reservations workspace.
    if (source === "reservations" || title.includes("no-show") || title.includes("booking") || title.includes("overbooking") || title.includes("reservation")) {
        return { label: "Review", href: "/dashboard/reservations" };
    }

    // Revenue / growth momentum → revenue forecast.
    if (title.includes("growth") || title.includes("revenue") || title.includes("momentum")) {
        return { label: "Review", href: "/dashboard/ai/revenue" };
    }

    // Fallback: the full insights view.
    return { label: "Review", href: "/dashboard/ai#insights" };
}
