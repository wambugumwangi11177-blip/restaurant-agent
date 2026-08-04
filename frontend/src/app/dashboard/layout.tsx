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
    Clock,
    Megaphone,
    Cpu,
} from "lucide-react";
import NotificationBell from "@/components/NotificationBell";

// adminOnly pages call management/AI endpoints that are ADMIN-gated on the
// backend (routers/ai.py, analytics.py — RBAC pass 2026-07-11). Hiding their nav
// entries from STAFF avoids sending floor staff to pages that would 403. STAFF
// (POS role) keep the operational pages: POS, Kitchen, Orders, Menu, Stock,
// Bookings, Sales (Sales reads /orders/, which stays staff-accessible).
const navItems = [
    { href: "/dashboard",              label: "Home",     icon: Home, adminOnly: true },
    { href: "/dashboard/pos",          label: "POS",      icon: CreditCard },
    { href: "/dashboard/kitchen",      label: "Kitchen",  icon: ChefHat },
    { href: "/dashboard/orders",       label: "Orders",   icon: ShoppingBag },
    { href: "/dashboard/menu",         label: "Menu",     icon: UtensilsCrossed },
    { href: "/dashboard/inventory",    label: "Stock",    icon: Package },
    { href: "/dashboard/reservations", label: "Bookings", icon: CalendarDays },
    { href: "/dashboard/sales",        label: "Sales",    icon: DollarSign },
    // The AI Command Center. Superseded /dashboard/insights, which served a
    // hardcoded Lavy demo and was deleted 2026-07-08.
    { href: "/dashboard/ai",           label: "AI",       icon: Brain, adminOnly: true },
    { href: "/dashboard/marketing",    label: "Growth",   icon: Megaphone, adminOnly: true },
    { href: "/dashboard/roi",          label: "ROI",      icon: Clock, adminOnly: true },
    // AI Ops shows this restaurant's OWN AI cost/reliability — ADMIN-only, like
    // the rest of /ai/* (it reads /ai/usage).
    { href: "/dashboard/ai-ops",       label: "AI Ops",   icon: Cpu, adminOnly: true },
];

// STAFF land here instead of /dashboard (Home is an admin analytics page).
const STAFF_HOME = "/dashboard/pos";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
    const { user, logout, isLoading } = useAuth();
    const router = useRouter();
    const pathname = usePathname();
    const [sidebarOpen, setSidebarOpen] = useState(false);

    const isStaff = ((user as any)?.role || "").toLowerCase() === "staff";

    useEffect(() => {
        if (!isLoading && !user) {
            router.push("/login");
            return;
        }
        // Keep STAFF out of admin-only pages entirely — the backend already
        // returns 403 there, so this avoids a broken page rather than enforcing
        // security (which lives server-side). Redirect to their POS home.
        if (!isLoading && user && isStaff) {
            const onAdminPage = navItems.some(
                (i) =>
                    i.adminOnly &&
                    // Home is "/dashboard" — match it exactly, never as a prefix,
                    // or it would swallow every /dashboard/* path (incl. POS).
                    (pathname === i.href ||
                        (i.href !== "/dashboard" && pathname.startsWith(i.href + "/")))
            );
            if (onAdminPage) router.push(STAFF_HOME);
        }
    }, [user, isLoading, isStaff, pathname, router]);

    if (isLoading) {
        return (
            <div className="min-h-screen flex items-center justify-center">
                <div className="w-6 h-6 border-2 border-[#d4a853] border-t-transparent rounded-full animate-spin" />
            </div>
        );
    }

    if (!user) return null;

    const restaurantName = (user as any).restaurant_name || "Your Restaurant";

    return (
        <div className="min-h-screen flex">
            {/* Sidebar */}
            <aside
                className={`fixed inset-y-0 left-0 z-50 w-56 bg-[#0f0f0f] border-r border-[#1a1a1a] transform transition-transform duration-200 lg:translate-x-0 ${
                    sidebarOpen ? "translate-x-0" : "-translate-x-full"
                }`}
            >
                {/* Brand */}
                <div className="px-5 py-5 border-b border-[#1a1a1a]">
                    <h1 className="text-lg font-bold text-[#e5e5e5] tracking-tight">Chakula</h1>
                    <p className="text-xs text-[#d4a853] mt-0.5 truncate font-medium">{restaurantName}</p>
                    <p className="text-xs text-[#525252] truncate">{user.email}</p>
                </div>

                {/* Nav */}
                <nav className="p-3 space-y-0.5">
                    {navItems
                        .filter((item) => !item.adminOnly || !isStaff)
                        .map((item) => {
                        const isActive = pathname === item.href || pathname.startsWith(item.href + "/");
                        return (
                            <Link
                                key={item.href}
                                href={item.href}
                                onClick={() => setSidebarOpen(false)}
                                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors ${
                                    isActive
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
                        onClick={() => { logout(); router.push("/login"); }}
                        className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-[#737373] hover:text-red-400 hover:bg-red-500/5 w-full transition-colors"
                    >
                        <LogOut className="w-4 h-4" />
                        <span className="font-medium">Logout</span>
                    </button>
                </div>
            </aside>

            {/* Mobile overlay */}
            {sidebarOpen && (
                <div
                    className="fixed inset-0 bg-black/60 z-40 lg:hidden"
                    onClick={() => setSidebarOpen(false)}
                />
            )}

            {/* Main */}
            <main className="flex-1 lg:ml-56 min-h-screen">
                <header className="sticky top-0 z-30 bg-[#0a0a0a]/90 backdrop-blur-sm border-b border-[#1a1a1a] px-5 py-3 flex items-center justify-between">
                    <button
                        onClick={() => setSidebarOpen(!sidebarOpen)}
                        className="lg:hidden text-[#737373] hover:text-[#e5e5e5]"
                    >
                        {sidebarOpen ? <X className="w-5 h-5" /> : <MenuIcon className="w-5 h-5" />}
                    </button>
                    <div className="flex items-center gap-4">
                        <NotificationBell />
                        <div className="text-xs text-[#525252]">{user.role}</div>
                    </div>
                </header>

                <div className="p-5 max-w-6xl">
                    {children}
                </div>
            </main>
        </div>
    );
}
