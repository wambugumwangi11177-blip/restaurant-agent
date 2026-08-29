"use client";

import {
    CreditCard, ShoppingBag, ChefHat, Package, UtensilsCrossed, CalendarDays,
    DollarSign, Truck, Megaphone, Users, Clock, Brain, Cpu, LifeBuoy,
} from "lucide-react";
import TierLayoutShell from "@/components/staff/TierLayoutShell";

const NAV = [
    { href: "/staff/manager/pos", label: "POS", icon: CreditCard },
    { href: "/staff/manager/orders", label: "Orders", icon: ShoppingBag },
    { href: "/staff/manager/kitchen", label: "Kitchen", icon: ChefHat },
    { href: "/staff/manager/inventory", label: "Stock", icon: Package },
    { href: "/staff/manager/menu", label: "Menu", icon: UtensilsCrossed },
    { href: "/staff/manager/reservations", label: "Bookings", icon: CalendarDays },
    { href: "/staff/manager/sales", label: "Sales", icon: DollarSign },
    { href: "/staff/manager/purchasing", label: "Purchasing", icon: Truck },
    { href: "/staff/manager/marketing", label: "Growth", icon: Megaphone },
    { href: "/staff/manager/staff", label: "Staff", icon: Users },
    { href: "/staff/manager/roi", label: "ROI", icon: Clock },
    { href: "/staff/manager/ai", label: "AI", icon: Brain },
    { href: "/staff/manager/ai-ops", label: "AI Ops", icon: Cpu },
    { href: "/staff/manager/support", label: "Support", icon: LifeBuoy },
];

export default function ManagerLayout({ children }: { children: React.ReactNode }) {
    return (
        <TierLayoutShell tier="manager" tierLabel="Manager" navItems={NAV}>
            {children}
        </TierLayoutShell>
    );
}
