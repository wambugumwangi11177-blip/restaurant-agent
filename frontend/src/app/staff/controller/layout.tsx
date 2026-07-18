"use client";

import { DollarSign, ShoppingBag, ShieldAlert, Truck, Clock, Brain, Cpu, LifeBuoy } from "lucide-react";
import TierLayoutShell from "@/components/staff/TierLayoutShell";

const NAV = [
    { href: "/staff/controller", label: "Variance", icon: ShieldAlert },
    { href: "/staff/controller/sales", label: "Sales", icon: DollarSign },
    { href: "/staff/controller/orders", label: "Orders", icon: ShoppingBag },
    { href: "/staff/controller/purchasing", label: "Purchasing", icon: Truck },
    { href: "/staff/controller/roi", label: "ROI", icon: Clock },
    { href: "/staff/controller/ai", label: "AI", icon: Brain },
    { href: "/staff/controller/ai-ops", label: "AI Ops", icon: Cpu },
    { href: "/staff/controller/support", label: "Support", icon: LifeBuoy },
];

export default function ControllerLayout({ children }: { children: React.ReactNode }) {
    return (
        <TierLayoutShell tier="controller" tierLabel="Controller" navItems={NAV}>
            {children}
        </TierLayoutShell>
    );
}
