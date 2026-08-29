"use client";

import { useEffect, useState, useCallback } from "react";
import api from "@/lib/api";
import { motion, AnimatePresence } from "framer-motion";
import {
    Plus,
    Minus,
    Trash2,
    CreditCard,
    Smartphone,
    Banknote,
    ShoppingBag,
    UtensilsCrossed,
    Truck,
    X,
    Check,
    User,
    Hash,
    StickyNote,
} from "lucide-react";
import FormField from "@/components/ui/FormField";
import { getErrorMessage } from "@/lib/errors";
import {
    queueOrder,
    replayPendingOrders,
    isNetworkFailure,
    getPendingOrders,
} from "@/lib/offlineOrderOutbox";

interface MenuItem {
    id: number;
    name: string;
    price: number;
    category: string;
    description?: string;
    is_available?: boolean;
}

interface CartItem {
    menuItem: MenuItem;
    quantity: number;
}

/**
 * Order-entry / point-of-sale workspace — extracted from the original
 * dashboard/pos/page.tsx unmodified. Reused as-is by every tier with `pos` =
 * RW (directive 015: Owner, Manager, Supervisor, Waiter — all full access,
 * no read-only variant exists for this route).
 */
export default function POSWorkspace() {
    const [menuItems, setMenuItems] = useState<MenuItem[]>([]);
    const [cart, setCart] = useState<CartItem[]>([]);
    const [selectedCategory, setSelectedCategory] = useState("All");
    const [orderType, setOrderType] = useState("dine_in");
    const [deliveryChannel, setDeliveryChannel] = useState("walk_in");
    const [paymentMethod, setPaymentMethod] = useState("pending");
    const [customerName, setCustomerName] = useState("");
    const [customerPhone, setCustomerPhone] = useState("");
    const [tableNumber, setTableNumber] = useState("");
    const [notes, setNotes] = useState("");
    const [loading, setLoading] = useState(true);
    const [submitting, setSubmitting] = useState(false);
    const [showSuccess, setShowSuccess] = useState(false);
    const [lastOrderId, setLastOrderId] = useState<number | null>(null);
    const [orderError, setOrderError] = useState("");
    const [showQueuedOffline, setShowQueuedOffline] = useState(false);
    const [pendingOfflineCount, setPendingOfflineCount] = useState(0);

    const refreshPendingCount = useCallback(() => {
        getPendingOrders().then((orders) => setPendingOfflineCount(orders.length)).catch(() => {});
    }, []);

    const syncPendingOrders = useCallback(async () => {
        const result = await replayPendingOrders((payload) => api.post("/orders/", payload));
        refreshPendingCount();
        return result;
    }, [refreshPendingCount]);

    useEffect(() => {
        api.get("/menu/").then((res) => {
            setMenuItems(res.data.filter((i: MenuItem) => i.is_available !== false));
            setLoading(false);
        }).catch(() => setLoading(false));

        // Audit remediation, Tier 4 item 10: replay anything queued from a
        // prior offline session on mount (covers the PWA being reopened after
        // connectivity returns), and again the moment the browser reports
        // it's back online (covers staying on this screen through a drop).
        refreshPendingCount();
        syncPendingOrders();
        window.addEventListener("online", syncPendingOrders);
        return () => window.removeEventListener("online", syncPendingOrders);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const categories = ["All", ...Array.from(new Set(menuItems.map((i) => i.category)))];
    const filteredItems = selectedCategory === "All"
        ? menuItems
        : menuItems.filter((i) => i.category === selectedCategory);

    const addToCart = useCallback((item: MenuItem) => {
        setCart((prev) => {
            const existing = prev.find((c) => c.menuItem.id === item.id);
            if (existing) {
                return prev.map((c) =>
                    c.menuItem.id === item.id ? { ...c, quantity: c.quantity + 1 } : c
                );
            }
            return [...prev, { menuItem: item, quantity: 1 }];
        });
    }, []);

    const updateQty = useCallback((itemId: number, delta: number) => {
        setCart((prev) =>
            prev
                .map((c) =>
                    c.menuItem.id === itemId
                        ? { ...c, quantity: Math.max(0, c.quantity + delta) }
                        : c
                )
                .filter((c) => c.quantity > 0)
        );
    }, []);

    const removeFromCart = useCallback((itemId: number) => {
        setCart((prev) => prev.filter((c) => c.menuItem.id !== itemId));
    }, []);

    const subtotal = cart.reduce((sum, c) => sum + c.menuItem.price * c.quantity, 0);
    const itemCount = cart.reduce((sum, c) => sum + c.quantity, 0);

    const handleSubmit = async () => {
        if (cart.length === 0) return;
        setSubmitting(true);
        setOrderError("");
        const payload = {
            items: cart.map((c) => ({
                menu_item_id: c.menuItem.id,
                quantity: c.quantity,
            })),
            order_type: orderType,
            delivery_channel: deliveryChannel,
            payment_method: paymentMethod,
            customer_name: customerName,
            customer_phone: customerPhone,
            table_number: tableNumber ? parseInt(tableNumber) : null,
            notes,
        };
        const resetForm = () => {
            setCart([]);
            setCustomerName("");
            setCustomerPhone("");
            setTableNumber("");
            setNotes("");
            setPaymentMethod("pending");
        };
        try {
            const res = await api.post("/orders/", payload);
            setLastOrderId(res.data.id);
            setShowSuccess(true);
            resetForm();
            setTimeout(() => setShowSuccess(false), 3000);
        } catch (err) {
            if (isNetworkFailure(err)) {
                // Audit remediation, Tier 4 item 10: no connectivity — queue
                // instead of dropping the order. The cart still clears (the
                // order IS captured, just not yet delivered), matching the
                // success path's UX rather than leaving a confusing half-state.
                await queueOrder(payload);
                refreshPendingCount();
                resetForm();
                setShowQueuedOffline(true);
                setTimeout(() => setShowQueuedOffline(false), 4000);
            } else {
                setOrderError(getErrorMessage(err, "Order failed — please try again."));
            }
        }
        setSubmitting(false);
    };

    const formatKES = (cents: number) =>
        `KES ${(cents / 100).toLocaleString("en-KE")}`;

    if (loading) {
        return (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 h-[calc(100vh-120px)]">
                <div className="lg:col-span-2 bg-surface rounded-xl animate-pulse" />
                <div className="bg-surface rounded-xl animate-pulse" />
            </div>
        );
    }

    return (
        <div className="flex flex-col h-[calc(100vh-120px)]">
            {/* Success toast */}
            <AnimatePresence>
                {showSuccess && (
                    <motion.div
                        initial={{ opacity: 0, y: -20 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -20 }}
                        className="fixed top-4 right-4 z-50 bg-success/10 border border-success/30 rounded-xl px-5 py-3 flex items-center gap-2"
                    >
                        <Check className="w-4 h-4 text-success" />
                        <span className="text-sm text-success">Order #{lastOrderId} sent to kitchen!</span>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Error toast */}
            <AnimatePresence>
                {orderError && (
                    <motion.div
                        role="status"
                        initial={{ opacity: 0, y: -20 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -20 }}
                        className="fixed top-4 right-4 z-50 bg-danger/10 border border-danger/30 rounded-xl px-5 py-3 flex items-center gap-2"
                    >
                        <X className="w-4 h-4 text-danger" />
                        <span className="text-sm text-danger">{orderError}</span>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Queued-offline toast — audit remediation, Tier 4 item 10 */}
            <AnimatePresence>
                {showQueuedOffline && (
                    <motion.div
                        role="status"
                        initial={{ opacity: 0, y: -20 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -20 }}
                        className="fixed top-4 right-4 z-50 bg-warning/10 border border-warning/30 rounded-xl px-5 py-3 flex items-center gap-2"
                    >
                        <ShoppingBag className="w-4 h-4 text-warning" />
                        <span className="text-sm text-warning">No connection — order saved, will send automatically once you&apos;re back online.</span>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Header */}
            <div className="flex items-center justify-between mb-4">
                <div>
                    <h1 className="text-xl font-bold text-text">New Order</h1>
                    <p className="text-xs text-text-dim">Tap items to add, then send to kitchen</p>
                </div>
                {pendingOfflineCount > 0 && (
                    <div
                        role="status"
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-warning/10 border border-warning/30 text-warning text-xs font-medium"
                    >
                        {pendingOfflineCount} order{pendingOfflineCount !== 1 ? "s" : ""} waiting to send
                    </div>
                )}
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 flex-1 min-h-0">
                {/* Left: Menu items */}
                <div className="lg:col-span-2 flex flex-col min-h-0">
                    {/* Category tabs */}
                    <div className="flex gap-1.5 mb-3 overflow-x-auto pb-1">
                        {categories.map((cat) => (
                            <button
                                key={cat}
                                onClick={() => setSelectedCategory(cat)}
                                className={`px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-all ${selectedCategory === cat
                                        ? "bg-accent text-black"
                                        : "bg-surface-hover text-text-muted hover:text-text"
                                    }`}
                            >
                                {cat}
                            </button>
                        ))}
                    </div>

                    {/* Items grid */}
                    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2 overflow-y-auto flex-1">
                        {filteredItems.map((item) => {
                            const inCart = cart.find((c) => c.menuItem.id === item.id);
                            return (
                                <motion.button
                                    key={item.id}
                                    whileTap={{ scale: 0.95 }}
                                    onClick={() => addToCart(item)}
                                    className={`relative bg-surface border rounded-xl p-3 text-left transition-all hover:border-accent/50 ${inCart ? "border-accent/40" : "border-border"
                                        }`}
                                >
                                    {inCart && (
                                        <span className="absolute -top-1.5 -right-1.5 bg-accent text-black text-[10px] font-bold w-5 h-5 rounded-full flex items-center justify-center">
                                            {inCart.quantity}
                                        </span>
                                    )}
                                    <p className="text-sm font-medium text-text truncate">{item.name}</p>
                                    <p className="text-xs text-accent mt-1">{formatKES(item.price)}</p>
                                    <p className="text-[10px] text-text-dim mt-0.5">{item.category}</p>
                                </motion.button>
                            );
                        })}
                    </div>
                </div>

                {/* Right: Cart & order details */}
                <div className="bg-surface border border-border rounded-xl flex flex-col min-h-0">
                    <div className="px-4 py-3 border-b border-surface-hover flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <ShoppingBag className="w-4 h-4 text-accent" />
                            <span className="text-sm font-semibold text-text">Cart</span>
                        </div>
                        <span className="text-[10px] text-text-dim">{itemCount} item{itemCount !== 1 ? "s" : ""}</span>
                    </div>

                    <div className="flex-1 overflow-y-auto px-4 py-2 space-y-2">
                        {cart.length === 0 ? (
                            <p className="text-xs text-text-dim text-center py-8">Tap items to add them here</p>
                        ) : (
                            cart.map((c) => (
                                <div key={c.menuItem.id} className="flex items-center gap-2 py-1.5">
                                    <div className="flex-1 min-w-0">
                                        <p className="text-xs text-text truncate">{c.menuItem.name}</p>
                                        <p className="text-[10px] text-accent">{formatKES(c.menuItem.price * c.quantity)}</p>
                                    </div>
                                    <div className="flex items-center gap-1">
                                        <button onClick={() => updateQty(c.menuItem.id, -1)}
                                            aria-label={`Decrease quantity of ${c.menuItem.name}`}
                                            className="w-6 h-6 rounded bg-surface-hover flex items-center justify-center text-text-muted hover:text-text">
                                            <Minus className="w-3 h-3" />
                                        </button>
                                        <span className="text-xs text-text w-5 text-center">{c.quantity}</span>
                                        <button onClick={() => updateQty(c.menuItem.id, 1)}
                                            aria-label={`Increase quantity of ${c.menuItem.name}`}
                                            className="w-6 h-6 rounded bg-surface-hover flex items-center justify-center text-text-muted hover:text-text">
                                            <Plus className="w-3 h-3" />
                                        </button>
                                        <button onClick={() => removeFromCart(c.menuItem.id)}
                                            aria-label={`Remove ${c.menuItem.name} from cart`}
                                            className="w-6 h-6 rounded flex items-center justify-center text-text-dim hover:text-danger">
                                            <Trash2 className="w-3 h-3" />
                                        </button>
                                    </div>
                                </div>
                            ))
                        )}
                    </div>

                    {/* Order details */}
                    <div className="border-t border-surface-hover px-4 py-3 space-y-3">
                        {/* Order type */}
                        <div className="flex gap-1.5">
                            {[
                                { v: "dine_in", label: "Dine In", icon: UtensilsCrossed },
                                { v: "takeout", label: "Takeaway", icon: ShoppingBag },
                                { v: "delivery", label: "Delivery", icon: Truck },
                            ].map((t) => (
                                <button key={t.v} onClick={() => setOrderType(t.v)}
                                    className={`flex-1 flex items-center justify-center gap-1 py-1.5 rounded-lg text-[10px] font-medium transition-all ${orderType === t.v
                                            ? "bg-accent/10 text-accent border border-accent/30"
                                            : "bg-surface-hover text-text-muted border border-transparent"
                                        }`}>
                                    <t.icon className="w-3 h-3" />
                                    {t.label}
                                </button>
                            ))}
                        </div>

                        {/* Delivery channel (only for delivery) */}
                        {orderType === "delivery" && (
                            <div className="flex gap-1.5">
                                {[
                                    { v: "uber_eats", label: "Uber Eats" },
                                    { v: "bolt_food", label: "Bolt Food" },
                                    { v: "glovo", label: "Glovo" },
                                    { v: "walk_in", label: "Direct" },
                                ].map((ch) => (
                                    <button key={ch.v} onClick={() => setDeliveryChannel(ch.v)}
                                        className={`flex-1 py-1.5 rounded-lg text-[10px] font-medium transition-all ${deliveryChannel === ch.v
                                                ? "bg-info/10 text-info border border-info/30"
                                                : "bg-surface-hover text-text-muted border border-transparent"
                                            }`}>
                                        {ch.label}
                                    </button>
                                ))}
                            </div>
                        )}

                        {/* Customer info */}
                        <div className="grid grid-cols-2 gap-2">
                            <div className="relative">
                                <User className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-text-dim" />
                                <FormField
                                    label="Customer name"
                                    srOnlyLabel
                                    type="text" placeholder="Name" value={customerName}
                                    onChange={(e) => setCustomerName(e.target.value)}
                                    className="w-full bg-surface-hover border border-border rounded-lg pl-7 pr-2 py-1.5 text-xs text-text placeholder-text-dim focus:border-accent/50 focus:outline-none"
                                />
                            </div>
                            {orderType === "dine_in" ? (
                                <div className="relative">
                                    <Hash className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-text-dim" />
                                    <FormField
                                        label="Table number"
                                        srOnlyLabel
                                        type="text" placeholder="Table #" value={tableNumber}
                                        onChange={(e) => setTableNumber(e.target.value)}
                                        className="w-full bg-surface-hover border border-border rounded-lg pl-7 pr-2 py-1.5 text-xs text-text placeholder-text-dim focus:border-accent/50 focus:outline-none"
                                    />
                                </div>
                            ) : (
                                <div className="relative">
                                    <Smartphone className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-text-dim" />
                                    <FormField
                                        label="Customer phone"
                                        srOnlyLabel
                                        type="text" placeholder="Phone" value={customerPhone}
                                        onChange={(e) => setCustomerPhone(e.target.value)}
                                        className="w-full bg-surface-hover border border-border rounded-lg pl-7 pr-2 py-1.5 text-xs text-text placeholder-text-dim focus:border-accent/50 focus:outline-none"
                                    />
                                </div>
                            )}
                        </div>

                        {/* Notes */}
                        <div className="relative">
                            <StickyNote className="absolute left-2 top-2 w-3 h-3 text-text-dim" />
                            <FormField
                                label="Order notes"
                                srOnlyLabel
                                type="text" placeholder="Notes (e.g. no onions, extra spicy)" value={notes}
                                onChange={(e) => setNotes(e.target.value)}
                                className="w-full bg-surface-hover border border-border rounded-lg pl-7 pr-2 py-1.5 text-xs text-text placeholder-text-dim focus:border-accent/50 focus:outline-none"
                            />
                        </div>

                        {/* Payment */}
                        <div className="flex gap-1.5">
                            {[
                                { v: "cash", label: "Cash", icon: Banknote },
                                { v: "mpesa", label: "M-Pesa", icon: Smartphone },
                                { v: "card", label: "Card", icon: CreditCard },
                                { v: "pending", label: "Later", icon: X },
                            ].map((p) => (
                                <button key={p.v} onClick={() => setPaymentMethod(p.v)}
                                    className={`flex-1 flex items-center justify-center gap-1 py-1.5 rounded-lg text-[10px] font-medium transition-all ${paymentMethod === p.v
                                            ? "bg-success/10 text-success border border-success/30"
                                            : "bg-surface-hover text-text-muted border border-transparent"
                                        }`}>
                                    <p.icon className="w-3 h-3" />
                                    {p.label}
                                </button>
                            ))}
                        </div>

                        {/* Total & submit */}
                        <div className="flex items-center justify-between pt-2 border-t border-surface-hover">
                            <div>
                                <p className="text-[10px] text-text-dim">Total</p>
                                <p className="text-lg font-bold text-accent">{formatKES(subtotal)}</p>
                            </div>
                            <button
                                onClick={handleSubmit}
                                disabled={cart.length === 0 || submitting}
                                className={`px-6 py-2.5 rounded-xl text-sm font-semibold transition-all ${cart.length > 0 && !submitting
                                        ? "bg-accent text-black hover:bg-[#c49843]"
                                        : "bg-border text-text-dim cursor-not-allowed"
                                    }`}
                            >
                                {submitting ? "Sending..." : "Send to Kitchen"}
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
