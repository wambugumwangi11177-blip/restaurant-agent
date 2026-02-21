"use client";

import { useAuth } from "@/context/AuthContext";
import { useRouter, usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import Link from "next/link";
import {
    Home,
    UtensilsCrossed,
    ShoppingBag,
    Package,
    CalendarDays,
    Brain,
    LogOut,
    Menu as MenuIcon,
    X,
    CreditCard,
    ChefHat,
    DollarSign,
} from "lucide-react";

const navItems = [
    { href: "/dashboard", label: "Home", icon: Home },
    { href: "/dashboard/pos", label: "POS", icon: CreditCard },
    { href: "/dashboard/kitchen", label: "Kitchen", icon: ChefHat },
    { href: "/dashboard/orders", label: "Orders", icon: ShoppingBag },
    { href: "/dashboard/menu", label: "Menu", icon: UtensilsCrossed },
    { href: "/dashboard/inventory", label: "Stock", icon: Package },
    { href: "/dashboard/reservations", label: "Bookings", icon: CalendarDays },
    { href: "/dashboard/sales", label: "Sales", icon: DollarSign },
    { href: "/dashboard/insights", label: "Insights", icon: Brain },
];

export default function DashboardLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    const { user, logout, isLoading } = useAuth();
    const router = useRouter();
    const pathname = usePathname();
    const [sidebarOpen, setSidebarOpen] = useState(false);

    useEffect(() => {
        if (!isLoading && !user) {
            router.push("/login");
        }
    }, [user, isLoading, router]);

    if (isLoading) {
        return (
            <div className="min-h-screen flex items-center justify-center">
                <div className="w-6 h-6 border-2 border-[#d4a853] border-t-transparent rounded-full animate-spin" />
            </div>
        );
    }

    if (!user) return null;

    return (
        <div className="min-h-screen flex">
            {/* Sidebar */}
            <aside
                className={`fixed inset-y-0 left-0 z-50 w-56 bg-[#0f0f0f] border-r border-[#1a1a1a] transform transition-transform duration-200 lg:translate-x-0 ${sidebarOpen ? "translate-x-0" : "-translate-x-full"
                    }`}
            >
                {/* Brand */}
                <div className="px-5 py-5 border-b border-[#1a1a1a]">
                    <h1 className="text-lg font-bold text-[#e5e5e5] tracking-tight">Chakula</h1>
                    <p className="text-xs text-[#525252] mt-0.5 truncate">{user.email}</p>
                </div>

                {/* Nav */}
                <nav className="p-3 space-y-0.5">
                    {navItems.map((item) => {
                        const isActive = pathname === item.href;
                        return (
                            <Link
                                key={item.href}
                                href={item.href}
                                onClick={() => setSidebarOpen(false)}
                                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors ${isActive
                                    ? "bg-[#1a1a1a] text-[#d4a853]"
                                    : "text-[#737373] hover:text-[#e5e5e5] hover:bg-[#141414]"
                                    }`}
                            >
                                <item.icon className="w-4 h-4" />
                                <span className="font-medium">{item.label}</span>
                            </Link>
                        );
                    })}
                </nav>

                {/* Logout */}
                <div className="absolute bottom-0 left-0 right-0 p-3 border-t border-[#1a1a1a]">
                    <button
                        onClick={() => {
                            logout();
                            router.push("/login");
                        }}
                        className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-[#737373] hover:text-red-400 hover:bg-red-500/5 w-full transition-colors"
                    >
                        <LogOut className="w-4 h-4" />
                        <span className="font-medium">Logout</span>
                    </button>
                </div>
            </aside>

            {/* Overlay */}
            {sidebarOpen && (
                <div
                    className="fixed inset-0 bg-black/60 z-40 lg:hidden"
                    onClick={() => setSidebarOpen(false)}
                />
            )}

            {/* Main */}
            <main className="flex-1 lg:ml-56 min-h-screen">
                {/* Top bar */}
                <header className="sticky top-0 z-30 bg-[#0a0a0a]/90 backdrop-blur-sm border-b border-[#1a1a1a] px-5 py-3 flex items-center justify-between">
                    <button
                        onClick={() => setSidebarOpen(!sidebarOpen)}
                        className="lg:hidden text-[#737373] hover:text-[#e5e5e5]"
                    >
                        {sidebarOpen ? <X className="w-5 h-5" /> : <MenuIcon className="w-5 h-5" />}
                    </button>
                    <div className="text-xs text-[#525252]">
                        {user.role}
                    </div>
                </header>

                <div className="p-5 max-w-6xl">
                    {children}
                </div>
            </main>
        </div>
    );
}
