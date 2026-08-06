"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { demoData, isOrdersEmpty, DEMO_DATA_ENABLED } from "@/lib/demo-data";
import { motion } from "framer-motion";
import {
    TrendingUp, Banknote, Smartphone, CreditCard,
    UtensilsCrossed, ShoppingBag, Truck, Crown,
} from "lucide-react";

interface Order {
    id: number;
    status: string;
    order_type: string;
    delivery_channel: string;
    payment_method: string;
    is_paid: boolean;
    total: number;
    created_at: string;
    items: { item_name: string; quantity: number; unit_price: number; menu_item_id?: number }[];
}

export default function SalesPage() {
    const [orders, setOrders] = useState<Order[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        api.get("/orders/").then((res) => {
            setOrders(res.data);
            setLoading(false);
        }).catch(() => setLoading(false));
    }, []);

    if (loading) {
        return (
            <div className="space-y-4">
                <div className="bg-[#141414] rounded-xl h-28 animate-pulse" />
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    {[...Array(4)].map((_, i) => (
                        <div key={i} className="bg-[#141414] rounded-xl h-24 animate-pulse" />
                    ))}
                </div>
            </div>
        );
    }

    // DEMO_DATA_ENABLED gates this in production — see lib/demo-data.ts.
    const isDemo = DEMO_DATA_ENABLED && isOrdersEmpty(orders);

    // Calculate real stats. Group by the STORED date string (YYYY-MM-DD) rather
    // than `new Date(created_at).toDateString()` — the timestamps are naive UTC,
    // and letting the browser parse them as local time shifts orders across the
    // day boundary (an EAT viewer saw every UTC-dated order land on the "wrong"
    // day, so "today" matched nothing → sales showed 0). Show the most recent
    // business day that actually has orders: that's real today for a live
    // restaurant, and the latest data day for the showcase — always non-empty.
    const dayKey = (s: string) => (s || "").slice(0, 10);
    const latestDay = orders.reduce((m, o) => (dayKey(o.created_at) > m ? dayKey(o.created_at) : m), "");
    const todayOrders = orders.filter((o) => dayKey(o.created_at) === latestDay);
    const completedToday = todayOrders.filter((o) => o.status !== "cancelled");

    const totalRevenue = completedToday.reduce((sum, o) => sum + (o.total || 0), 0);
    const totalOrders = completedToday.length;
    const avgOrder = totalOrders > 0 ? totalRevenue / totalOrders : 0;
    const unpaidOrders = completedToday.filter((o) => !o.is_paid);

    const byCash = completedToday.filter((o) => o.payment_method === "cash");
    const byMpesa = completedToday.filter((o) => o.payment_method === "mpesa");
    const byCard = completedToday.filter((o) => o.payment_method === "card");
    const byPending = completedToday.filter((o) => o.payment_method === "pending");

    const byDineIn = completedToday.filter((o) => o.order_type === "dine_in");
    const byTakeout = completedToday.filter((o) => o.order_type === "takeout");
    const byDelivery = completedToday.filter((o) => o.order_type === "delivery");
    const byUber = completedToday.filter((o) => o.delivery_channel === "uber_eats");
    const byBolt = completedToday.filter((o) => o.delivery_channel === "bolt_food");
    const byGlovo = completedToday.filter((o) => o.delivery_channel === "glovo");
    const byApp = completedToday.filter((o) => o.delivery_channel === "app");

    const itemSales: Record<string, { name: string; qty: number; revenue: number }> = {};
    completedToday.forEach((o) => {
        (o.items || []).forEach((item) => {
            const key = item.item_name || `item-${item.menu_item_id}`;
            if (!itemSales[key]) itemSales[key] = { name: key, qty: 0, revenue: 0 };
            itemSales[key].qty += item.quantity;
            itemSales[key].revenue += item.unit_price * item.quantity;
        });
    });
    const topItems = Object.values(itemSales).sort((a, b) => b.revenue - a.revenue).slice(0, 8);

    const hourlyData: Record<number, number> = {};
    completedToday.forEach((o) => {
        const h = new Date(o.created_at).getHours();
        hourlyData[h] = (hourlyData[h] || 0) + o.total;
    });
    const maxHourlyRevenue = Math.max(...Object.values(hourlyData), 1);

    // Demo values
    const demoRevenue = demoData.revenue;
    const maxDemoRevenue = Math.max(...demoRevenue.map((d) => d.revenue));
    const demoTopSellers = demoData.topSellers;

    const formatKES = (v: number) => {
        if (!v) return "KES 0";
        return `KES ${v.toLocaleString("en-KE", { maximumFractionDigits: 0 })}`;
    };

    return (
        <div className="space-y-5">
            {/* Header */}
            <div>
                <h1 className="text-xl font-bold text-[#e5e5e5]">Sales</h1>
                <p className="text-sm text-[#525252] mt-0.5">
                    {isDemo ? "Last 7 days performance" : "Today's performance"}
                </p>
            </div>

            {/* Demo Banner */}
            {isDemo && (
                <div className="flex items-center gap-2 px-3 py-1.5 bg-[#d4a853]/8 border border-[#d4a853]/20 rounded-lg">
                    <span className="text-[10px] text-[#d4a853]">📊 Demo Mode — Showing sample data for Lavy restaurant</span>
                </div>
            )}

            {/* Quick stats */}
            {isDemo ? (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    <StatCard label="Revenue (7d)" value={`KES ${(484000).toLocaleString("en-KE")}`} color="#d4a853" />
                    <StatCard label="Orders (7d)" value="438" color="#3b82f6" />
                    <StatCard label="Avg Order" value="KES 2,114" color="#22c55e" />
                    <StatCard label="Top Day" value="Saturday" color="#8b5cf6" />
                </div>
            ) : (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    <StatCard label="Revenue Today" value={formatKES(totalRevenue)} color="#d4a853" />
                    <StatCard label="Orders" value={`${totalOrders}`} color="#3b82f6" />
                    <StatCard label="Avg Order" value={formatKES(avgOrder)} color="#22c55e" />
                    <StatCard label="Unpaid" value={`${unpaidOrders.length}`} color={unpaidOrders.length > 0 ? "#ef4444" : "#22c55e"} />
                </div>
            )}

            {/* Demo: Weekly Revenue Chart */}
            {isDemo && (
                <div className="bg-[#141414] border border-[#262626] rounded-xl">
                    <div className="px-4 py-3 border-b border-[#1a1a1a] flex items-center gap-2">
                        <TrendingUp className="w-3.5 h-3.5 text-[#d4a853]" />
                        <h2 className="text-sm font-semibold text-[#e5e5e5]">Revenue — Last 7 Days</h2>
                    </div>
                    <div className="px-4 py-4">
                        <div className="flex items-end gap-2 h-40">
                            {demoRevenue.map((day, i) => {
                                const pct = (day.revenue / maxDemoRevenue) * 100;
                                const isBest = day.revenue === maxDemoRevenue;
                                return (
                                    <motion.div
                                        key={day.date}
                                        initial={{ height: 0, opacity: 0 }}
                                        animate={{ height: `${pct}%`, opacity: 1 }}
                                        transition={{ delay: i * 0.06, duration: 0.4 }}
                                        className="flex-1 flex flex-col items-center gap-1 justify-end h-full"
                                    >
                                        <span className="text-[9px] text-[#525252]">
                                            {(day.revenue / 1000).toFixed(0)}k
                                        </span>
                                        <div
                                            className={`w-full rounded-t transition-all ${isBest ? "bg-[#d4a853]" : "bg-[#d4a853]/25"}`}
                                            style={{ height: `${pct}%` }}
                                        />
                                        <span className={`text-[10px] ${isBest ? "text-[#d4a853] font-semibold" : "text-[#525252]"}`}>
                                            {day.date}
                                        </span>
                                    </motion.div>
                                );
                            })}
                        </div>
                    </div>
                </div>
            )}

            {/* Real: Payment & Channel breakdown */}
            {!isDemo && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div className="bg-[#141414] border border-[#262626] rounded-xl">
                        <div className="px-4 py-3 border-b border-[#1a1a1a]">
                            <h2 className="text-sm font-semibold text-[#e5e5e5]">Payment Breakdown</h2>
                        </div>
                        <div className="px-4 py-3 space-y-3">
                            <PaymentRow icon={Banknote} label="Cash" count={byCash.length} total={byCash.reduce((s, o) => s + o.total, 0)} color="#22c55e" formatKES={formatKES} />
                            <PaymentRow icon={Smartphone} label="M-Pesa" count={byMpesa.length} total={byMpesa.reduce((s, o) => s + o.total, 0)} color="#22c55e" formatKES={formatKES} />
                            <PaymentRow icon={CreditCard} label="Card" count={byCard.length} total={byCard.reduce((s, o) => s + o.total, 0)} color="#3b82f6" formatKES={formatKES} />
                            {byPending.length > 0 && (
                                <PaymentRow icon={CreditCard} label="Unpaid" count={byPending.length} total={byPending.reduce((s, o) => s + o.total, 0)} color="#ef4444" formatKES={formatKES} />
                            )}
                        </div>
                    </div>
                    <div className="bg-[#141414] border border-[#262626] rounded-xl">
                        <div className="px-4 py-3 border-b border-[#1a1a1a]">
                            <h2 className="text-sm font-semibold text-[#e5e5e5]">Order Channels</h2>
                        </div>
                        <div className="px-4 py-3 space-y-3">
                            <ChannelRow icon={UtensilsCrossed} label="Dine In" count={byDineIn.length} total={byDineIn.reduce((s, o) => s + o.total, 0)} color="#d4a853" formatKES={formatKES} />
                            <ChannelRow icon={ShoppingBag} label="Takeaway" count={byTakeout.length} total={byTakeout.reduce((s, o) => s + o.total, 0)} color="#3b82f6" formatKES={formatKES} />
                            <ChannelRow icon={Truck} label="Delivery" count={byDelivery.length} total={byDelivery.reduce((s, o) => s + o.total, 0)} color="#eab308" formatKES={formatKES} />
                            {byUber.length > 0 && <ChannelRow icon={Truck} label="  ↳ Uber Eats" count={byUber.length} total={byUber.reduce((s, o) => s + o.total, 0)} color="#525252" formatKES={formatKES} nested />}
                            {byBolt.length > 0 && <ChannelRow icon={Truck} label="  ↳ Bolt Food" count={byBolt.length} total={byBolt.reduce((s, o) => s + o.total, 0)} color="#525252" formatKES={formatKES} nested />}
                            {byGlovo.length > 0 && <ChannelRow icon={Truck} label="  ↳ Glovo" count={byGlovo.length} total={byGlovo.reduce((s, o) => s + o.total, 0)} color="#525252" formatKES={formatKES} nested />}
                            {byApp.length > 0 && <ChannelRow icon={Smartphone} label="  ↳ App Orders" count={byApp.length} total={byApp.reduce((s, o) => s + o.total, 0)} color="#525252" formatKES={formatKES} nested />}
                        </div>
                    </div>
                </div>
            )}

            {/* Real: Hourly chart */}
            {!isDemo && Object.keys(hourlyData).length > 0 && (
                <div className="bg-[#141414] border border-[#262626] rounded-xl">
                    <div className="px-4 py-3 border-b border-[#1a1a1a]">
                        <h2 className="text-sm font-semibold text-[#e5e5e5]">Sales by Hour</h2>
                    </div>
                    <div className="px-4 py-4">
                        <div className="flex items-end gap-1 h-32">
                            {Array.from({ length: 18 }, (_, i) => i + 6).map((hour) => {
                                const val = hourlyData[hour] || 0;
                                const pct = (val / maxHourlyRevenue) * 100;
                                const isNow = new Date().getHours() === hour;
                                return (
                                    <div key={hour} className="flex-1 flex flex-col items-center gap-1">
                                        <div className="w-full relative" style={{ height: `${Math.max(pct, 2)}%` }}>
                                            <div className={`w-full h-full rounded-t ${isNow ? "bg-[#d4a853]" : "bg-[#d4a853]/20"}`} />
                                        </div>
                                        <span className={`text-[8px] ${isNow ? "text-[#d4a853]" : "text-[#525252]"}`}>
                                            {hour > 12 ? `${hour - 12}p` : hour === 12 ? "12p" : `${hour}a`}
                                        </span>
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                </div>
            )}

            {/* Top Sellers — demo or real */}
            {(isDemo || topItems.length > 0) && (
                <div className="bg-[#141414] border border-[#262626] rounded-xl">
                    <div className="px-4 py-3 border-b border-[#1a1a1a] flex items-center gap-2">
                        <Crown className="w-3.5 h-3.5 text-[#d4a853]" />
                        <h2 className="text-sm font-semibold text-[#e5e5e5]">
                            {isDemo ? "Top Sellers — This Week" : "Top Sellers Today"}
                        </h2>
                    </div>
                    <div className="divide-y divide-[#1a1a1a]">
                        {isDemo
                            ? demoTopSellers.map((item, i) => (
                                <motion.div
                                    key={item.name}
                                    initial={{ opacity: 0, x: -8 }}
                                    animate={{ opacity: 1, x: 0 }}
                                    transition={{ delay: i * 0.06 }}
                                    className="px-4 py-2.5 flex items-center gap-3"
                                >
                                    <span className="text-xs font-bold text-[#525252] w-4">{i + 1}</span>
                                    <div className="flex-1">
                                        <p className="text-xs text-[#e5e5e5]">{item.name}</p>
                                        <p className="text-[10px] text-[#525252]">{item.orders} sold · {item.margin}% margin</p>
                                    </div>
                                    <span className="text-xs font-semibold text-[#d4a853]">
                                        KES {item.revenue.toLocaleString("en-KE")}
                                    </span>
                                </motion.div>
                            ))
                            : topItems.map((item, i) => (
                                <div key={item.name} className="px-4 py-2.5 flex items-center gap-3">
                                    <span className="text-xs font-bold text-[#525252] w-4">{i + 1}</span>
                                    <div className="flex-1">
                                        <p className="text-xs text-[#e5e5e5]">{item.name}</p>
                                        <p className="text-[10px] text-[#525252]">{item.qty} sold</p>
                                    </div>
                                    <span className="text-xs font-semibold text-[#d4a853]">{formatKES(item.revenue)}</span>
                                </div>
                            ))
                        }
                    </div>
                </div>
            )}
        </div>
    );
}

function StatCard({ label, value, color }: { label: string; value: string; color: string }) {
    return (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
            className="bg-[#141414] border border-[#262626] rounded-xl px-4 py-3">
            <p className="text-[10px] text-[#525252] uppercase tracking-wider">{label}</p>
            <p className="text-lg font-bold mt-0.5" style={{ color }}>{value}</p>
        </motion.div>
    );
}

function PaymentRow({ icon: Icon, label, count, total, color, formatKES }: any) {
    return (
        <div className="flex items-center gap-3">
            <Icon className="w-4 h-4" style={{ color }} />
            <div className="flex-1"><p className="text-xs text-[#e5e5e5]">{label}</p></div>
            <span className="text-[10px] text-[#525252]">{count} orders</span>
            <span className="text-xs font-semibold text-[#e5e5e5] w-24 text-right">{formatKES(total)}</span>
        </div>
    );
}

function ChannelRow({ icon: Icon, label, count, total, color, formatKES, nested }: any) {
    return (
        <div className={`flex items-center gap-3 ${nested ? "pl-4 opacity-70" : ""}`}>
            <Icon className="w-3.5 h-3.5" style={{ color }} />
            <div className="flex-1"><p className="text-xs text-[#e5e5e5]">{label}</p></div>
            <span className="text-[10px] text-[#525252]">{count}</span>
            <span className="text-xs font-semibold text-[#e5e5e5] w-24 text-right">{formatKES(total)}</span>
        </div>
    );
}
