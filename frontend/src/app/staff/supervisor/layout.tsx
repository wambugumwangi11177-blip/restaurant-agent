"use client";

import { CreditCard, ShoppingBag, ChefHat, CalendarDays, DollarSign, Truck, UtensilsCrossed, LifeBuoy } from "lucide-react";
import TierLayoutShell from "@/components/staff/TierLayoutShell";

const NAV = [
    { href: "/staff/supervisor", label: "POS", icon: CreditCard },
    { href: "/staff/supervisor/orders", label: "Orders", icon: ShoppingBag },
    { href: "/staff/supervisor/kitchen", label: "Kitchen", icon: ChefHat },
    // permissions.ts already granted Supervisor read access to `menu` — no
    // page existed to use it (found during the notification-routing audit
    // below, same class of gap as the purchasing page above).
    { href: "/staff/supervisor/menu", label: "Menu", icon: UtensilsCrossed },
    { href: "/staff/supervisor/reservations", label: "Bookings", icon: CalendarDays },
    { href: "/staff/supervisor/sales", label: "Sales", icon: DollarSign },
    // Supervisor approves purchase orders (backend's _CAN_APPROVE) but had no
    // page to reach them from until this — see routers/purchase_orders.py.
    { href: "/staff/supervisor/purchasing", label: "Purchasing", icon: Truck },
    { href: "/staff/supervisor/support", label: "Support", icon: LifeBuoy },
];

export default function SupervisorLayout({ children }: { children: React.ReactNode }) {
    return (
        <TierLayoutShell tier="supervisor" tierLabel="Supervisor" navItems={NAV}>
            {children}
        </TierLayoutShell>
    );
}
