"use client";

import { CreditCard, ShoppingBag, CalendarDays, ChefHat, UtensilsCrossed, LifeBuoy } from "lucide-react";
import TierLayoutShell from "@/components/staff/TierLayoutShell";

const NAV = [
    { href: "/staff/waiter", label: "POS", icon: CreditCard },
    { href: "/staff/waiter/orders", label: "Orders", icon: ShoppingBag },
    { href: "/staff/waiter/reservations", label: "Bookings", icon: CalendarDays },
    { href: "/staff/waiter/kitchen", label: "Kitchen", icon: ChefHat },
    { href: "/staff/waiter/menu", label: "Menu", icon: UtensilsCrossed },
    { href: "/staff/waiter/support", label: "Support", icon: LifeBuoy },
];

export default function WaiterLayout({ children }: { children: React.ReactNode }) {
    return (
        <TierLayoutShell tier="waiter" tierLabel="Waiter" navItems={NAV}>
            {children}
        </TierLayoutShell>
    );
}
