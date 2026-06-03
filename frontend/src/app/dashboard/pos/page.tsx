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

export default function POSPage() {
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

    useEffect(() => {
        api.get("/menu/").then((res) => {
            setMenuItems(res.data.filter((i: MenuItem) => i.is_available !== false));
            setLoading(false);
        }).catch(() => setLoading(false));
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
        try {
            const res = await api.post("/orders/", {
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
            });
            setLastOrderId(res.data.id);
            setShowSuccess(true);
            // Reset
            setCart([]);
            setCustomerName("");
            setCustomerPhone("");
            setTableNumber("");
            setNotes("");
            setPaymentMethod("pending");
            setTimeout(() => setShowSuccess(false), 3000);
        } catch (err) {
            console.error("Order failed:", err);
        }
        setSubmitting(false);
    };

    const formatKES = (cents: number) =>
        `KES ${(cents / 100).toLocaleString("en-KE")}`;

    if (loading) {
        return (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 h-[calc(100vh-120px)]">
                <div className="lg:col-span-2 bg-[#141414] rounded-xl animate-pulse" />
                <div className="bg-[#141414] rounded-xl animate-pulse" />
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
                        className="fixed top-4 right-4 z-50 bg-[#22c55e]/10 border border-[#22c55e]/30 rounded-xl px-5 py-3 flex items-center gap-2"
                    >
                        <Check className="w-4 h-4 text-[#22c55e]" />
                        <span className="text-sm text-[#22c55e]">Order #{lastOrderId} sent to kitchen!</span>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Header */}
            <div className="flex items-center justify-between mb-4">
                <div>
                    <h1 className="text-xl font-bold text-[#e5e5e5]">New Order</h1>
                    <p className="text-xs text-[#525252]">Tap items to add, then send to kitchen</p>
                </div>
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
                                        ? "bg-[#d4a853] text-black"
                                        : "bg-[#1a1a1a] text-[#737373] hover:text-[#e5e5e5]"
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
                                    className={`relative bg-[#141414] border rounded-xl p-3 text-left transition-all hover:border-[#d4a853]/50 ${inCart ? "border-[#d4a853]/40" : "border-[#262626]"
                                        }`}
                                >
                                    {inCart && (
                                        <span className="absolute -top-1.5 -right-1.5 bg-[#d4a853] text-black text-[10px] font-bold w-5 h-5 rounded-full flex items-center justify-center">
                                            {inCart.quantity}
                                        </span>
                                    )}
                                    <p className="text-sm font-medium text-[#e5e5e5] truncate">{item.name}</p>
                                    <p className="text-xs text-[#d4a853] mt-1">{formatKES(item.price)}</p>
                                    <p className="text-[10px] text-[#525252] mt-0.5">{item.category}</p>
                                </motion.button>
                            );
                        })}
                    </div>
                </div>

                {/* Right: Cart & order details */}
                <div className="bg-[#141414] border border-[#262626] rounded-xl flex flex-col min-h-0">
                    <div className="px-4 py-3 border-b border-[#1a1a1a] flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <ShoppingBag className="w-4 h-4 text-[#d4a853]" />
                            <span className="text-sm font-semibold text-[#e5e5e5]">Cart</span>
                        </div>
                        <span className="text-[10px] text-[#525252]">{itemCount} item{itemCount !== 1 ? "s" : ""}</span>
                    </div>

                    <div className="flex-1 overflow-y-auto px-4 py-2 space-y-2">
                        {cart.length === 0 ? (
                            <p className="text-xs text-[#525252] text-center py-8">Tap items to add them here</p>
                        ) : (
                            cart.map((c) => (
                                <div key={c.menuItem.id} className="flex items-center gap-2 py-1.5">
                                    <div className="flex-1 min-w-0">
                                        <p className="text-xs text-[#e5e5e5] truncate">{c.menuItem.name}</p>
                                        <p className="text-[10px] text-[#d4a853]">{formatKES(c.menuItem.price * c.quantity)}</p>
                                    </div>
                                    <div className="flex items-center gap-1">
                                        <button onClick={() => updateQty(c.menuItem.id, -1)}
                                            className="w-6 h-6 rounded bg-[#1a1a1a] flex items-center justify-center text-[#737373] hover:text-[#e5e5e5]">
                                            <Minus className="w-3 h-3" />
                                        </button>
                                        <span className="text-xs text-[#e5e5e5] w-5 text-center">{c.quantity}</span>
                                        <button onClick={() => updateQty(c.menuItem.id, 1)}
                                            className="w-6 h-6 rounded bg-[#1a1a1a] flex items-center justify-center text-[#737373] hover:text-[#e5e5e5]">
                                            <Plus className="w-3 h-3" />
                                        </button>
                                        <button onClick={() => removeFromCart(c.menuItem.id)}
                                            className="w-6 h-6 rounded flex items-center justify-center text-[#525252] hover:text-[#ef4444]">
                                            <Trash2 className="w-3 h-3" />
                                        </button>
                                    </div>
                                </div>
                            ))
                        )}
                    </div>

                    {/* Order details */}
                    <div className="border-t border-[#1a1a1a] px-4 py-3 space-y-3">
                        {/* Order type */}
                        <div className="flex gap-1.5">
                            {[
                                { v: "dine_in", label: "Dine In", icon: UtensilsCrossed },
                                { v: "takeout", label: "Takeaway", icon: ShoppingBag },
                                { v: "delivery", label: "Delivery", icon: Truck },
                            ].map((t) => (
                                <button key={t.v} onClick={() => setOrderType(t.v)}
                                    className={`flex-1 flex items-center justify-center gap-1 py-1.5 rounded-lg text-[10px] font-medium transition-all ${orderType === t.v
                                            ? "bg-[#d4a853]/10 text-[#d4a853] border border-[#d4a853]/30"
                                            : "bg-[#1a1a1a] text-[#737373] border border-transparent"
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
                                                ? "bg-[#3b82f6]/10 text-[#3b82f6] border border-[#3b82f6]/30"
                                                : "bg-[#1a1a1a] text-[#737373] border border-transparent"
                                            }`}>
                                        {ch.label}
                                    </button>
                                ))}
                            </div>
                        )}

                        {/* Customer info */}
                        <div className="grid grid-cols-2 gap-2">
                            <div className="relative">
                                <User className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-[#525252]" />
                                <input
                                    type="text" placeholder="Name" value={customerName}
                                    onChange={(e) => setCustomerName(e.target.value)}
                                    className="w-full bg-[#1a1a1a] border border-[#262626] rounded-lg pl-7 pr-2 py-1.5 text-xs text-[#e5e5e5] placeholder-[#525252] focus:border-[#d4a853]/50 focus:outline-none"
                                />
                            </div>
                            {orderType === "dine_in" ? (
                                <div className="relative">
                                    <Hash className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-[#525252]" />
                                    <input
                                        type="text" placeholder="Table #" value={tableNumber}
                                        onChange={(e) => setTableNumber(e.target.value)}
                                        className="w-full bg-[#1a1a1a] border border-[#262626] rounded-lg pl-7 pr-2 py-1.5 text-xs text-[#e5e5e5] placeholder-[#525252] focus:border-[#d4a853]/50 focus:outline-none"
                                    />
                                </div>
                            ) : (
                                <div className="relative">
                                    <Smartphone className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-[#525252]" />
                                    <input
                                        type="text" placeholder="Phone" value={customerPhone}
                                        onChange={(e) => setCustomerPhone(e.target.value)}
                                        className="w-full bg-[#1a1a1a] border border-[#262626] rounded-lg pl-7 pr-2 py-1.5 text-xs text-[#e5e5e5] placeholder-[#525252] focus:border-[#d4a853]/50 focus:outline-none"
                                    />
                                </div>
                            )}
                        </div>

                        {/* Notes */}
                        <div className="relative">
                            <StickyNote className="absolute left-2 top-2 w-3 h-3 text-[#525252]" />
                            <input
                                type="text" placeholder="Notes (e.g. no onions, extra spicy)" value={notes}
                                onChange={(e) => setNotes(e.target.value)}
                                className="w-full bg-[#1a1a1a] border border-[#262626] rounded-lg pl-7 pr-2 py-1.5 text-xs text-[#e5e5e5] placeholder-[#525252] focus:border-[#d4a853]/50 focus:outline-none"
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
                                            ? "bg-[#22c55e]/10 text-[#22c55e] border border-[#22c55e]/30"
                                            : "bg-[#1a1a1a] text-[#737373] border border-transparent"
                                        }`}>
                                    <p.icon className="w-3 h-3" />
                                    {p.label}
                                </button>
                            ))}
                        </div>

                        {/* Total & submit */}
                        <div className="flex items-center justify-between pt-2 border-t border-[#1a1a1a]">
                            <div>
                                <p className="text-[10px] text-[#525252]">Total</p>
                                <p className="text-lg font-bold text-[#d4a853]">{formatKES(subtotal)}</p>
                            </div>
                            <button
                                onClick={handleSubmit}
                                disabled={cart.length === 0 || submitting}
                                className={`px-6 py-2.5 rounded-xl text-sm font-semibold transition-all ${cart.length > 0 && !submitting
                                        ? "bg-[#d4a853] text-black hover:bg-[#c49843]"
                                        : "bg-[#262626] text-[#525252] cursor-not-allowed"
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
