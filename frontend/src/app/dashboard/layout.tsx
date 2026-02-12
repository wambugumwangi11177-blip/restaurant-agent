"use client";

import { useAuth } from "@/context/AuthContext";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import {
    Brain,
    ChefHat,
    Package,
    CalendarRange,
    BarChart3,
    LogOut,
    Menu as MenuIcon,
    X,
    UtensilsCrossed,
    TrendingUp,
    Flame,
    Box,
    BookOpen,
} from "lucide-react";

const navItems = [
    { href: "/dashboard", label: "AI Overview", icon: Brain },
    { href: "/dashboard/menu", label: "Menu Engineering", icon: UtensilsCrossed },
    { href: "/dashboard/orders", label: "Revenue & Orders", icon: TrendingUp },
    { href: "/dashboard/inventory", label: "Inventory Intel", icon: Box },
    { href: "/dashboard/reservations", label: "Reservations", icon: CalendarRange },
];

export default function DashboardLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    const { user, logout, isLoading } = useAuth();
    const router = useRouter();
    const [sidebarOpen, setSidebarOpen] = useState(false);

    useEffect(() => {
        if (!isLoading && !user) {
            router.push("/login");
        }
    }, [user, isLoading, router]);

    if (isLoading) {
        return (
            <div className="min-h-screen flex items-center justify-center">
                <Brain className="w-10 h-10 text-indigo-400 animate-pulse" />
            </div>
        );
    }

    if (!user) return null;

    return (
        <div className="min-h-screen flex">
            {/* Sidebar */}
            <aside
                className={`fixed inset-y-0 left-0 z-50 w-64 glass transform transition-transform duration-300 lg:translate-x-0 ${sidebarOpen ? "translate-x-0" : "-translate-x-full"
                    }`}
            >
                <div className="flex items-center gap-3 p-6 border-b border-gray-800">
                    <div className="w-10 h-10 rounded-xl bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center">
                        <Brain className="w-5 h-5 text-indigo-400" />
                    </div>
                    <div>
                        <h1 className="font-bold text-white">AI Restaurant OS</h1>
                        <p className="text-xs text-gray-500">{user.email}</p>
                    </div>
                </div>

                <nav className="p-4 space-y-1">
                    {navItems.map((item) => (
                        <Link
                            key={item.href}
                            href={item.href}
                            onClick={() => setSidebarOpen(false)}
                            className="flex items-center gap-3 px-4 py-3 rounded-xl text-gray-400 hover:text-white hover:bg-gray-800/50 transition-all group"
                        >
                            <item.icon className="w-5 h-5 group-hover:text-indigo-400 transition-colors" />
                            <span className="text-sm font-medium">{item.label}</span>
                        </Link>
                    ))}
                </nav>

                <div className="absolute bottom-0 left-0 right-0 p-4 border-t border-gray-800">
                    <button
                        onClick={() => {
                            logout();
                            router.push("/login");
                        }}
                        className="flex items-center gap-3 px-4 py-3 rounded-xl text-gray-400 hover:text-red-400 hover:bg-red-500/10 transition-all w-full"
                    >
                        <LogOut className="w-5 h-5" />
                        <span className="text-sm font-medium">Logout</span>
                    </button>
                </div>
            </aside>

            {/* Overlay */}
            {sidebarOpen && (
                <div
                    className="fixed inset-0 bg-black/50 z-40 lg:hidden"
                    onClick={() => setSidebarOpen(false)}
                />
            )}

            {/* Main Content */}
            <main className="flex-1 lg:ml-64">
                {/* Top Bar */}
                <header className="sticky top-0 z-30 glass px-6 py-4 flex items-center justify-between">
                    <button
                        onClick={() => setSidebarOpen(!sidebarOpen)}
                        className="lg:hidden text-gray-400 hover:text-white"
                    >
                        {sidebarOpen ? <X className="w-6 h-6" /> : <MenuIcon className="w-6 h-6" />}
                    </button>
                    <div className="text-sm text-gray-500">
                        Role: <span className="text-indigo-400 font-medium">{user.role}</span>
                    </div>
                </header>

                <div className="p-6">
                    <motion.div
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.3 }}
                    >
                        {children}
                    </motion.div>
                </div>
            </main>
        </div>
    );
}
