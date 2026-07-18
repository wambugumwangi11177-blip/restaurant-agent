"use client";

import { ChefHat, ShoppingBag, UtensilsCrossed, Package, LifeBuoy } from "lucide-react";
import TierLayoutShell from "@/components/staff/TierLayoutShell";

const NAV = [
    { href: "/staff/kitchen", label: "Kitchen", icon: ChefHat },
    { href: "/staff/kitchen/orders", label: "Orders", icon: ShoppingBag },
    // Directive 017's kitchen "pull" requisition — request an ingredient
    // from the store and confirm what arrives. Backend has always allowed
    // this (routers/stock_custody.py); this page was the missing frontend.
    { href: "/staff/kitchen/stock", label: "Stock", icon: Package },
    { href: "/staff/kitchen/menu", label: "Menu", icon: UtensilsCrossed },
    { href: "/staff/kitchen/support", label: "Support", icon: LifeBuoy },
];

export default function KitchenLayout({ children }: { children: React.ReactNode }) {
    return (
        <TierLayoutShell tier="kitchen" tierLabel="Kitchen" navItems={NAV}>
            {children}
        </TierLayoutShell>
    );
}
