"use client";

import { Package, Truck, LifeBuoy } from "lucide-react";
import TierLayoutShell from "@/components/staff/TierLayoutShell";

const NAV = [
    { href: "/staff/stockkeeper", label: "Stock", icon: Package },
    { href: "/staff/stockkeeper/purchasing", label: "Purchasing", icon: Truck },
    { href: "/staff/stockkeeper/support", label: "Support", icon: LifeBuoy },
];

export default function StockkeeperLayout({ children }: { children: React.ReactNode }) {
    return (
        <TierLayoutShell tier="stockkeeper" tierLabel="Stockkeeper" navItems={NAV}>
            {children}
        </TierLayoutShell>
    );
}
