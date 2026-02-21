"use client";

import { useEffect, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
    Plus,
    Minus,
    Trash2,
    ShoppingCart,
    Phone,
    User,
    MapPin,
    ArrowLeft,
    Check,
    Smartphone,
} from "lucide-react";

interface MenuItem {
    id: number;
    name: string;
    price: number;
    category: string;
    description?: string;
}

interface CartItem {
    menuItem: MenuItem;
    quantity: number;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
const RESTAURANT_ID = 1; // Default restaurant

export default function CustomerOrderPage() {
    const [menuItems, setMenuItems] = useState<MenuItem[]>([]);
    const [cart, setCart] = useState<CartItem[]>([]);
    const [selectedCategory, setSelectedCategory] = useState("All");
    const [step, setStep] = useState<"menu" | "checkout" | "confirmed">("menu");
    const [customerName, setCustomerName] = useState("");
    const [customerPhone, setCustomerPhone] = useState("");
    const [orderType, setOrderType] = useState("takeout");
    const [notes, setNotes] = useState("");
    const [loading, setLoading] = useState(true);
    const [submitting, setSubmitting] = useState(false);
    const [orderId, setOrderId] = useState<number | null>(null);

    useEffect(() => {
        fetch(`${API_URL}/menu/public/${RESTAURANT_ID}`)
            .then((r) => r.json())
            .then((data) => {
                setMenuItems(data);
                setLoading(false);
            })
            .catch(() => setLoading(false));
    }, []);

    const categories = ["All", ...Array.from(new Set(menuItems.map((i) => i.category)))];
    const filteredItems = selectedCategory === "All" ? menuItems : menuItems.filter((i) => i.category === selectedCategory);

    const addToCart = useCallback((item: MenuItem) => {
        setCart((prev) => {
            const existing = prev.find((c) => c.menuItem.id === item.id);
            if (existing) return prev.map((c) => c.menuItem.id === item.id ? { ...c, quantity: c.quantity + 1 } : c);
            return [...prev, { menuItem: item, quantity: 1 }];
        });
    }, []);

    const updateQty = useCallback((itemId: number, delta: number) => {
        setCart((prev) => prev.map((c) => c.menuItem.id === itemId ? { ...c, quantity: Math.max(0, c.quantity + delta) } : c).filter((c) => c.quantity > 0));
    }, []);

    const subtotal = cart.reduce((sum, c) => sum + c.menuItem.price * c.quantity, 0);
    const itemCount = cart.reduce((sum, c) => sum + c.quantity, 0);

    const formatKES = (cents: number) => `KES ${(cents / 100).toLocaleString("en-KE")}`;

    const handleSubmit = async () => {
        if (cart.length === 0 || !customerName || !customerPhone) return;
        setSubmitting(true);
        try {
            const res = await fetch(`${API_URL}/orders/public?restaurant_id=${RESTAURANT_ID}`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    items: cart.map((c) => ({ menu_item_id: c.menuItem.id, quantity: c.quantity })),
                    order_type: orderType,
                    delivery_channel: "app",
                    payment_method: "pending",
                    customer_name: customerName,
                    customer_phone: customerPhone,
                    notes,
                }),
            });
            const data = await res.json();
            setOrderId(data.id);
            setStep("confirmed");
        } catch (err) {
            console.error("Order failed:", err);
        }
        setSubmitting(false);
    };

    if (loading) {
        return (
            <div className="min-h-screen bg-[#0a0a0a] flex items-center justify-center">
                <div className="w-8 h-8 border-2 border-[#d4a853] border-t-transparent rounded-full animate-spin" />
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-[#0a0a0a] text-[#e5e5e5]">
            {/* Header */}
            <header className="sticky top-0 z-40 bg-[#0a0a0a]/90 backdrop-blur-xl border-b border-[#262626]">
                <div className="max-w-2xl mx-auto px-4 py-3 flex items-center justify-between">
                    <div>
                        <h1 className="text-lg font-bold text-[#d4a853]">Chakula</h1>
                        <p className="text-[10px] text-[#525252]">Order fresh food, delivered or pickup</p>
                    </div>
                    {step === "menu" && itemCount > 0 && (
                        <button
                            onClick={() => setStep("checkout")}
                            className="flex items-center gap-2 px-4 py-2 bg-[#d4a853] text-black rounded-xl text-sm font-semibold"
                        >
                            <ShoppingCart className="w-4 h-4" />
                            {itemCount} · {formatKES(subtotal)}
                        </button>
                    )}
                    {step === "checkout" && (
                        <button onClick={() => setStep("menu")} className="flex items-center gap-1 text-sm text-[#737373]">
                            <ArrowLeft className="w-4 h-4" />
                            Back
                        </button>
                    )}
                </div>
            </header>

            <main className="max-w-2xl mx-auto px-4 py-4">
                <AnimatePresence mode="wait">
                    {step === "menu" && (
                        <motion.div key="menu" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                            {/* Categories */}
                            <div className="flex gap-2 mb-4 overflow-x-auto pb-1">
                                {categories.map((cat) => (
                                    <button key={cat} onClick={() => setSelectedCategory(cat)}
                                        className={`px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-all ${selectedCategory === cat
                                                ? "bg-[#d4a853] text-black"
                                                : "bg-[#1a1a1a] text-[#737373]"
                                            }`}>
                                        {cat}
                                    </button>
                                ))}
                            </div>

                            {/* Menu items */}
                            <div className="space-y-2">
                                {filteredItems.map((item) => {
                                    const inCart = cart.find((c) => c.menuItem.id === item.id);
                                    return (
                                        <motion.div key={item.id} layout
                                            className="bg-[#141414] border border-[#262626] rounded-xl p-4 flex items-center justify-between">
                                            <div className="flex-1">
                                                <p className="text-sm font-medium text-[#e5e5e5]">{item.name}</p>
                                                {item.description && (
                                                    <p className="text-xs text-[#525252] mt-0.5">{item.description}</p>
                                                )}
                                                <p className="text-sm font-semibold text-[#d4a853] mt-1">{formatKES(item.price)}</p>
                                            </div>
                                            <div className="flex items-center gap-2 ml-4">
                                                {inCart ? (
                                                    <div className="flex items-center gap-2">
                                                        <button onClick={() => updateQty(item.id, -1)}
                                                            className="w-8 h-8 rounded-full bg-[#1a1a1a] flex items-center justify-center text-[#737373]">
                                                            <Minus className="w-4 h-4" />
                                                        </button>
                                                        <span className="text-sm font-bold w-4 text-center">{inCart.quantity}</span>
                                                        <button onClick={() => updateQty(item.id, 1)}
                                                            className="w-8 h-8 rounded-full bg-[#d4a853]/10 flex items-center justify-center text-[#d4a853]">
                                                            <Plus className="w-4 h-4" />
                                                        </button>
                                                    </div>
                                                ) : (
                                                    <button onClick={() => addToCart(item)}
                                                        className="w-8 h-8 rounded-full bg-[#d4a853]/10 flex items-center justify-center text-[#d4a853]">
                                                        <Plus className="w-4 h-4" />
                                                    </button>
                                                )}
                                            </div>
                                        </motion.div>
                                    );
                                })}
                            </div>
                        </motion.div>
                    )}

                    {step === "checkout" && (
                        <motion.div key="checkout" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }}>
                            <h2 className="text-lg font-bold mb-4">Your Order</h2>

                            {/* Cart items */}
                            <div className="bg-[#141414] border border-[#262626] rounded-xl divide-y divide-[#1a1a1a] mb-4">
                                {cart.map((c) => (
                                    <div key={c.menuItem.id} className="px-4 py-3 flex items-center justify-between">
                                        <div>
                                            <p className="text-sm text-[#e5e5e5]">{c.quantity}× {c.menuItem.name}</p>
                                            <p className="text-xs text-[#d4a853]">{formatKES(c.menuItem.price * c.quantity)}</p>
                                        </div>
                                        <div className="flex items-center gap-1">
                                            <button onClick={() => updateQty(c.menuItem.id, -1)}
                                                className="w-6 h-6 rounded bg-[#1a1a1a] flex items-center justify-center text-[#737373]">
                                                <Minus className="w-3 h-3" />
                                            </button>
                                            <button onClick={() => updateQty(c.menuItem.id, 1)}
                                                className="w-6 h-6 rounded bg-[#1a1a1a] flex items-center justify-center text-[#737373]">
                                                <Plus className="w-3 h-3" />
                                            </button>
                                        </div>
                                    </div>
                                ))}
                                <div className="px-4 py-3 flex justify-between">
                                    <span className="text-sm font-semibold text-[#e5e5e5]">Total</span>
                                    <span className="text-sm font-bold text-[#d4a853]">{formatKES(subtotal)}</span>
                                </div>
                            </div>

                            {/* Order type */}
                            <div className="flex gap-2 mb-4">
                                {[
                                    { v: "takeout", label: "Pickup" },
                                    { v: "delivery", label: "Delivery" },
                                    { v: "dine_in", label: "Dine In" },
                                ].map((t) => (
                                    <button key={t.v} onClick={() => setOrderType(t.v)}
                                        className={`flex-1 py-2.5 rounded-xl text-sm font-medium transition-all ${orderType === t.v
                                                ? "bg-[#d4a853]/10 text-[#d4a853] border border-[#d4a853]/30"
                                                : "bg-[#1a1a1a] text-[#737373] border border-[#262626]"
                                            }`}>
                                        {t.label}
                                    </button>
                                ))}
                            </div>

                            {/* Customer details */}
                            <div className="space-y-3 mb-4">
                                <div className="relative">
                                    <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#525252]" />
                                    <input type="text" placeholder="Your name" value={customerName}
                                        onChange={(e) => setCustomerName(e.target.value)}
                                        className="w-full bg-[#141414] border border-[#262626] rounded-xl pl-10 pr-4 py-3 text-sm text-[#e5e5e5] placeholder-[#525252] focus:border-[#d4a853]/50 focus:outline-none"
                                    />
                                </div>
                                <div className="relative">
                                    <Phone className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#525252]" />
                                    <input type="tel" placeholder="Phone number (e.g. 0712 345 678)" value={customerPhone}
                                        onChange={(e) => setCustomerPhone(e.target.value)}
                                        className="w-full bg-[#141414] border border-[#262626] rounded-xl pl-10 pr-4 py-3 text-sm text-[#e5e5e5] placeholder-[#525252] focus:border-[#d4a853]/50 focus:outline-none"
                                    />
                                </div>
                                <input type="text" placeholder="Any special requests? (optional)" value={notes}
                                    onChange={(e) => setNotes(e.target.value)}
                                    className="w-full bg-[#141414] border border-[#262626] rounded-xl px-4 py-3 text-sm text-[#e5e5e5] placeholder-[#525252] focus:border-[#d4a853]/50 focus:outline-none"
                                />
                            </div>

                            {/* Payment info */}
                            <div className="bg-[#eab308]/5 border border-[#eab308]/20 rounded-xl px-4 py-3 mb-4">
                                <div className="flex items-center gap-2">
                                    <Smartphone className="w-4 h-4 text-[#eab308]" />
                                    <p className="text-xs text-[#eab308]">
                                        You&apos;ll pay when you pick up or receive your order. M-Pesa, cash, or card accepted.
                                    </p>
                                </div>
                            </div>

                            {/* Submit */}
                            <button
                                onClick={handleSubmit}
                                disabled={!customerName || !customerPhone || submitting}
                                className={`w-full py-3.5 rounded-xl text-sm font-semibold transition-all ${customerName && customerPhone && !submitting
                                        ? "bg-[#d4a853] text-black hover:bg-[#c49843]"
                                        : "bg-[#262626] text-[#525252] cursor-not-allowed"
                                    }`}
                            >
                                {submitting ? "Placing Order..." : `Place Order · ${formatKES(subtotal)}`}
                            </button>
                        </motion.div>
                    )}

                    {step === "confirmed" && (
                        <motion.div key="confirmed" initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}
                            className="text-center py-16">
                            <div className="w-16 h-16 bg-[#22c55e]/10 rounded-full flex items-center justify-center mx-auto mb-4">
                                <Check className="w-8 h-8 text-[#22c55e]" />
                            </div>
                            <h2 className="text-xl font-bold text-[#e5e5e5] mb-2">Order Placed!</h2>
                            <p className="text-sm text-[#737373] mb-1">Your order #{orderId} is being prepared</p>
                            <p className="text-xs text-[#525252] mb-6">We&apos;ll let you know when it&apos;s ready</p>
                            <button onClick={() => { setStep("menu"); setCart([]); setOrderId(null); }}
                                className="px-6 py-2.5 bg-[#1a1a1a] border border-[#262626] rounded-xl text-sm text-[#737373] hover:text-[#e5e5e5]">
                                Order Again
                            </button>
                        </motion.div>
                    )}
                </AnimatePresence>
            </main>
        </div>
    );
}
