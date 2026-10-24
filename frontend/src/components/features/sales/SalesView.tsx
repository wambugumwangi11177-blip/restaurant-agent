"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { kes, shortDay, weekday } from "@/lib/owner/format";
import {
    TrendingUp, Banknote, Smartphone, CreditCard,
    UtensilsCrossed, ShoppingBag, Truck, Crown,
} from "lucide-react";
import StatCard from "@/components/ui/StatCard";
import Bars from "@/components/charts/Bars";
import PaymentRow from "./PaymentRow";
import ChannelRow from "./ChannelRow";

type Named = { key: string; label: string; count: number; kes: number };
type SalesToday = {
    window_label: string;
    service_day: string;
    revenue_kes: number;
    orders: number;
    avg_kes: number;
    unpaid: number;
    by_payment: Named[];
    by_channel: Named[];
    hourly: { hour: number; label: string; kes: number }[];
    top_items: { name: string; qty: number; kes: number }[];
};

/**
 * Sales analytics — extracted from the original dashboard/sales/page.tsx
 * unmodified. Purely a read-only display (no write actions), so it's reused
 * as-is by every tier with `sales` access (directive 015: Owner/Manager RW,
 * Supervisor/Controller R — RW vs R is moot here since nothing here mutates
 * data).
 */
export default function SalesView() {
    const [figures, setFigures] = useState<SalesToday | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        api.get<SalesToday>("/api/v1/sales/today")
            .then((res) => setFigures(res.data))
            .catch(() => setFigures(null))
            .finally(() => setLoading(false));
    }, []);

    if (loading) {
        return (
            <div className="space-y-4">
                <div className="bg-surface rounded-xl h-28 animate-pulse" />
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    {[...Array(4)].map((_, i) => (
                        <div key={i} className="bg-surface rounded-xl h-24 animate-pulse" />
                    ))}
                </div>
            </div>
        );
    }

    // An empty account gets an honest empty state. The total is the server's, not a page of orders.
    if (!figures || (figures.orders === 0 && figures.unpaid === 0 && figures.revenue_kes === 0)) {
        return (
            <div className="flex flex-col items-center justify-center min-h-[40vh] text-center space-y-3 px-6">
                <div className="w-12 h-12 rounded-2xl bg-[var(--accent)]/10 flex items-center justify-center">
                    <TrendingUp className="w-6 h-6 text-[var(--accent)]" />
                </div>
                <p className="text-sm text-text-muted max-w-sm">
                    No sales yet. Your revenue, payment breakdown, hourly trends, and top sellers
                    will appear here once you start recording orders.
                </p>
            </div>
        );
    }

    const totalRevenue = figures.revenue_kes;
    const totalOrders = figures.orders;
    const avgOrder = figures.avg_kes;
    const dayLabel = `${weekday(figures.service_day)} ${shortDay(figures.service_day)}`;
    const formatKES = (v: number) => kes(v);
    const pay = (key: string) => figures.by_payment.find((p) => p.key === key);
    const channel = (key: string) => figures.by_channel.find((p) => p.key === key);

    return (
        <div className="space-y-5">
            {/* Header */}
            <div>
                <h1 className="text-xl font-bold text-text">Sales</h1>
                <p className="text-sm text-text-dim mt-0.5">{figures.window_label} · {dayLabel}. Counted on the server, same paid total as Home.</p>
            </div>

            {/* Quick stats */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <StatCard label="Revenue Today" value={formatKES(totalRevenue)} color="#d4a853" />
                <StatCard label="Orders" value={`${totalOrders}`} color="#3b82f6" />
                <StatCard label="Avg Order" value={formatKES(avgOrder)} color="#22c55e" />
                <StatCard label="Unpaid" value={`${figures.unpaid}`} color={figures.unpaid > 0 ? "#ef4444" : "#22c55e"} />
            </div>

            {/* Payment & channel breakdown */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="bg-surface border border-border rounded-xl">
                    <div className="px-4 py-3 border-b border-surface-hover">
                        <h2 className="text-sm font-semibold text-text">Payment Breakdown</h2>
                    </div>
                    <div className="px-4 py-3 space-y-3">
                        <PaymentRow icon={Banknote} label="Cash" count={pay("cash")?.count ?? 0} total={pay("cash")?.kes ?? 0} color="#22c55e" formatKES={formatKES} />
                        <PaymentRow icon={Smartphone} label="M-Pesa" count={pay("mpesa")?.count ?? 0} total={pay("mpesa")?.kes ?? 0} color="#22c55e" formatKES={formatKES} />
                        <PaymentRow icon={CreditCard} label="Card" count={pay("card")?.count ?? 0} total={pay("card")?.kes ?? 0} color="#3b82f6" formatKES={formatKES} />
                    </div>
                </div>
                <div className="bg-surface border border-border rounded-xl">
                    <div className="px-4 py-3 border-b border-surface-hover">
                        <h2 className="text-sm font-semibold text-text">Order Channels</h2>
                    </div>
                    <div className="px-4 py-3 space-y-3">
                        <ChannelRow icon={UtensilsCrossed} label="Dine In" count={channel("dine_in")?.count ?? 0} total={channel("dine_in")?.kes ?? 0} color="#d4a853" formatKES={formatKES} />
                        <ChannelRow icon={ShoppingBag} label="Takeaway" count={channel("takeout")?.count ?? 0} total={channel("takeout")?.kes ?? 0} color="#3b82f6" formatKES={formatKES} />
                        <ChannelRow icon={Truck} label="Delivery" count={channel("delivery")?.count ?? 0} total={channel("delivery")?.kes ?? 0} color="#eab308" formatKES={formatKES} />
                        {(channel("uber_eats")?.count ?? 0) > 0 && <ChannelRow icon={Truck} label="  ↳ Uber Eats" count={channel("uber_eats")!.count} total={channel("uber_eats")!.kes} color="#525252" formatKES={formatKES} nested />}
                        {(channel("bolt_food")?.count ?? 0) > 0 && <ChannelRow icon={Truck} label="  ↳ Bolt Food" count={channel("bolt_food")!.count} total={channel("bolt_food")!.kes} color="#525252" formatKES={formatKES} nested />}
                        {(channel("glovo")?.count ?? 0) > 0 && <ChannelRow icon={Truck} label="  ↳ Glovo" count={channel("glovo")!.count} total={channel("glovo")!.kes} color="#525252" formatKES={formatKES} nested />}
                        {(channel("app")?.count ?? 0) > 0 && <ChannelRow icon={Smartphone} label="  ↳ App Orders" count={channel("app")!.count} total={channel("app")!.kes} color="#525252" formatKES={formatKES} nested />}
                    </div>
                </div>
            </div>

            <div className="bg-surface border border-border rounded-xl">
                <div className="px-4 py-3 border-b border-surface-hover">
                    <h2 className="text-sm font-semibold text-text">Sales by hour</h2>
                    <p className="text-[10px] text-text-dim">Nairobi time, {figures.window_label.toLowerCase()}.</p>
                </div>
                <div className="px-4 py-4">
                    <Bars
                        label={`Sales by hour on ${dayLabel}`}
                        bars={figures.hourly.map((h) => ({ key: String(h.hour), label: h.label, value: h.kes, title: `${h.label}: ${kes(h.kes)}` }))}
                        format={(v) => kes(v)}
                        state={figures.hourly.length ? undefined : "no_data"}
                        reason="Hourly sales appear once a paid order is recorded on this service day."
                    />
                </div>
            </div>

            {figures.top_items.length > 0 && (
                <div className="bg-surface border border-border rounded-xl">
                    <div className="px-4 py-3 border-b border-surface-hover flex items-center gap-2">
                        <Crown className="w-3.5 h-3.5 text-[var(--accent)]" />
                        <h2 className="text-sm font-semibold text-text">Top Sellers Today</h2>
                    </div>
                    <div className="divide-y divide-surface-hover">
                        {figures.top_items.map((item, i) => (
                            <div key={item.name} className="px-4 py-2.5 flex items-center gap-3">
                                <span className="text-xs font-bold text-text-dim w-4">{i + 1}</span>
                                <div className="flex-1">
                                    <p className="text-xs text-text">{item.name}</p>
                                    <p className="text-[10px] text-text-dim">{item.qty} sold</p>
                                </div>
                                <span className="text-xs font-semibold text-[var(--accent)]">{formatKES(item.kes)}</span>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}
