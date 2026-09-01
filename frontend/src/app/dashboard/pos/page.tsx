"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import api from "@/lib/api";
import {
    addToCart as addToCartPure,
    updateQty as updateQtyPure,
    removeFromCart as removeFromCartPure,
    cartSubtotal,
    cartItemCount,
    cartToOrderItems,
    lineUnitPrice,
    type MenuItem,
    type CartItem,
    type ModifierOption,
    type ModifierGroup,
} from "@/lib/cart";
import {
    enqueueOrder,
    watchOfflineQueue,
    getQueueLength,
    newClientId,
    errorStatus,
    isTerminalClientError,
} from "@/lib/offlineQueue";
import { PinSwitcher, type PinOperator } from "@/components/pos/PinSwitcher";
import { readOperator, writeOperator } from "@/lib/posOperator";
import { formatKES } from "@/lib/format";
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
    AlertTriangle,
    CloudOff,
    Search,
    PauseCircle,
    PlayCircle,
    Percent,
    Printer,
    Layers,
    DollarSign,
    Lock,
    Unlock,
    Receipt,
    RefreshCw,
} from "lucide-react";

interface ParkedTicket {
    id: string;
    label: string;
    cart: CartItem[];
    tableNumber: string;
    customerName: string;
    customerPhone: string;
    orderType: string;
    deliveryChannel: string;
    notes: string;
    parkedAt: string;
}

interface SplitPayment {
    method: "cash" | "mpesa" | "card";
    amountKES: number;
    reference: string;
}

interface TillState {
    id: number;
    opening_float_cents: number;
    status: string;
    opened_at: string;
}

export default function POSPage() {
    const [menuItems, setMenuItems] = useState<MenuItem[]>([]);
    const [cart, setCart] = useState<CartItem[]>([]);
    const [selectedCategory, setSelectedCategory] = useState("All");
    const [searchQuery, setSearchQuery] = useState("");
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
    const [lastOrder, setLastOrder] = useState<any | null>(null);
    const [errorMessage, setErrorMessage] = useState<string | null>(null);
    const [queuedMessage, setQueuedMessage] = useState<string | null>(null);
    const [queueLength, setQueueLength] = useState(0);
    const [activeOperator, setActiveOperator] = useState<PinOperator | null>(null);

    // Modifiers & Line notes modal state
    const [modifierItem, setModifierItem] = useState<MenuItem | null>(null);
    const [selectedMods, setSelectedMods] = useState<ModifierOption[]>([]);
    const [itemLineNote, setItemLineNote] = useState("");

    // Discount state
    const [discountType, setDiscountType] = useState<"percent" | "amount">("percent");
    const [discountValue, setDiscountValue] = useState<number>(0);
    const [discountReason, setDiscountReason] = useState("");
    const [showDiscountModal, setShowDiscountModal] = useState(false);

    // Parked tickets
    const [parkedTickets, setParkedTickets] = useState<ParkedTicket[]>([]);
    const [showParkedModal, setShowParkedModal] = useState(false);

    // Split Payment Modal
    const [showSplitModal, setShowSplitModal] = useState(false);
    const [splitPayments, setSplitPayments] = useState<SplitPayment[]>([
        { method: "cash", amountKES: 0, reference: "" },
        { method: "mpesa", amountKES: 0, reference: "" },
        { method: "card", amountKES: 0, reference: "" },
    ]);

    // Till Session State
    const [activeTill, setActiveTill] = useState<TillState | null>(null);
    const [showTillModal, setShowTillModal] = useState(false);
    const [openingFloat, setOpeningFloat] = useState<number>(5000); // 5,000 KES default float
    const [closingCashCount, setClosingCashCount] = useState<number>(0);
    const [varianceReason, setVarianceReason] = useState("");
    const [tillXReport, setTillXReport] = useState<any | null>(null);

    // Receipt Modal
    const [showReceiptModal, setShowReceiptModal] = useState(false);

    // Load Menu & Active Till
    const fetchMenuAndTill = useCallback(() => {
        api.get("/menu/").then((res) => {
            setMenuItems(res.data);
            setLoading(false);
        }).catch(() => setLoading(false));

        api.get("/orders/tills/current").then((res) => {
            if (res.data) setActiveTill(res.data);
        }).catch(() => {});
    }, []);

    useEffect(() => {
        fetchMenuAndTill();
    }, [fetchMenuAndTill]);

    // Restore operator & offline watcher
    useEffect(() => {
        const stored = readOperator();
        if (stored) setActiveOperator(stored);
    }, []);

    const switchOperator = useCallback((operator: PinOperator) => {
        setActiveOperator(operator);
        writeOperator(operator);
    }, []);

    useEffect(() => {
        setQueueLength(getQueueLength());
        const stop = watchOfflineQueue({
            onFlushed: () => {
                setQueueLength(getQueueLength());
                setQueuedMessage("A queued order synced to the kitchen.");
                setTimeout(() => setQueuedMessage(null), 3000);
            },
            onDropped: () => {
                setQueueLength(getQueueLength());
                setErrorMessage("A queued order was rejected and could not be sent — please re-enter it.");
            },
        });
        return stop;
    }, []);

    // Restore parked tickets
    useEffect(() => {
        try {
            const raw = localStorage.getItem("chakula_parked_tickets");
            if (raw) setParkedTickets(JSON.parse(raw));
        } catch {}
    }, []);

    const saveParkedTickets = (tickets: ParkedTicket[]) => {
        setParkedTickets(tickets);
        localStorage.setItem("chakula_parked_tickets", JSON.stringify(tickets));
    };

    // Filter categories & items
    const categories = useMemo(() => ["All", ...Array.from(new Set(menuItems.map((i) => i.category)))], [menuItems]);
    const filteredItems = useMemo(() => {
        return menuItems.filter((i) => {
            const matchesCat = selectedCategory === "All" || i.category === selectedCategory;
            const matchesSearch = !searchQuery.trim() || i.name.toLowerCase().includes(searchQuery.toLowerCase()) || i.category.toLowerCase().includes(searchQuery.toLowerCase());
            return matchesCat && matchesSearch;
        });
    }, [menuItems, selectedCategory, searchQuery]);

    // Handle Item Tap
    const handleItemClick = (item: MenuItem) => {
        if (item.is_available === false) return;
        if (item.modifier_groups && item.modifier_groups.length > 0) {
            setModifierItem(item);
            setSelectedMods([]);
            setItemLineNote("");
        } else {
            setCart((prev) => addToCartPure(prev, item));
        }
    };

    const confirmModifierItem = () => {
        if (!modifierItem) return;
        setCart((prev) => addToCartPure(prev, modifierItem, selectedMods, itemLineNote));
        setModifierItem(null);
        setSelectedMods([]);
        setItemLineNote("");
    };

    // Toggle 86
    const toggle86 = async (e: React.MouseEvent, item: MenuItem) => {
        e.stopPropagation();
        try {
            const res = await api.post(`/menu/${item.id}/toggle-86`);
            setMenuItems((prev) =>
                prev.map((i) => (i.id === item.id ? { ...i, is_available: res.data.is_available } : i))
            );
        } catch {}
    };

    const rawSubtotalCents = cartSubtotal(cart);
    const discountCents = useMemo(() => {
        if (discountValue <= 0) return 0;
        if (discountType === "percent") {
            return Math.round((rawSubtotalCents * discountValue) / 100);
        }
        return Math.min(rawSubtotalCents, discountValue * 100);
    }, [rawSubtotalCents, discountType, discountValue]);

    const finalTotalCents = Math.max(0, rawSubtotalCents - discountCents);
    const itemCount = cartItemCount(cart);

    // Park Ticket
    const parkCurrentTicket = () => {
        if (cart.length === 0) return;
        const ticket: ParkedTicket = {
            id: `parked_${Date.now()}`,
            label: tableNumber ? `Table ${tableNumber}` : (customerName || `Ticket #${parkedTickets.length + 1}`),
            cart,
            tableNumber,
            customerName,
            customerPhone,
            orderType,
            deliveryChannel,
            notes,
            parkedAt: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        };
        const updated = [...parkedTickets, ticket];
        saveParkedTickets(updated);
        setCart([]);
        setCustomerName("");
        setCustomerPhone("");
        setTableNumber("");
        setNotes("");
    };

    const recallParkedTicket = (ticket: ParkedTicket) => {
        setCart(ticket.cart);
        setTableNumber(ticket.tableNumber);
        setCustomerName(ticket.customerName);
        setCustomerPhone(ticket.customerPhone);
        setOrderType(ticket.orderType);
        setDeliveryChannel(ticket.deliveryChannel);
        setNotes(ticket.notes);
        saveParkedTickets(parkedTickets.filter((t) => t.id !== ticket.id));
        setShowParkedModal(false);
    };

    // Till Operations
    const handleOpenTill = async () => {
        try {
            const res = await api.post("/orders/tills/open", { opening_float_cents: openingFloat * 100 });
            setActiveTill(res.data);
            setShowTillModal(false);
        } catch (err: any) {
            setErrorMessage(err.response?.data?.detail || "Could not open till");
        }
    };

    const handleFetchXReport = async () => {
        if (!activeTill) return;
        try {
            const res = await api.get(`/orders/tills/${activeTill.id}/x-report`);
            setTillXReport(res.data);
        } catch {}
    };

    const handleCloseTill = async () => {
        if (!activeTill) return;
        try {
            await api.post(`/orders/tills/${activeTill.id}/close`, {
                closing_counted_cents: closingCashCount * 100,
                variance_reason: varianceReason,
            });
            setActiveTill(null);
            setTillXReport(null);
            setShowTillModal(false);
        } catch (err: any) {
            setErrorMessage(err.response?.data?.detail || "Could not close till");
        }
    };

    // Order Submission
    const handleSubmitOrder = async (splitPayload?: SplitPayment[]) => {
        if (cart.length === 0) return;
        setSubmitting(true);
        setErrorMessage(null);

        const paymentsList = splitPayload
            ? splitPayload.filter((p) => p.amountKES > 0).map((p) => ({
                  payment_method: p.method,
                  amount_cents: Math.round(p.amountKES * 100),
                  reference: p.reference,
              }))
            : [];

        const orderPayload = {
            items: cartToOrderItems(cart),
            order_type: orderType,
            delivery_channel: deliveryChannel,
            payment_method: paymentsList.length > 0 ? paymentsList[0].payment_method : paymentMethod,
            customer_name: customerName,
            customer_phone: customerPhone,
            table_number: tableNumber ? parseInt(tableNumber) : null,
            notes,
            discount_cents: discountCents,
            discount_reason: discountReason,
            payments: paymentsList,
            attributed_user_id: activeOperator?.id ?? null,
            idempotency_key: newClientId(),
        };

        const resetForm = () => {
            setCart([]);
            setCustomerName("");
            setCustomerPhone("");
            setTableNumber("");
            setNotes("");
            setDiscountValue(0);
            setDiscountReason("");
            setPaymentMethod("pending");
            setShowSplitModal(false);
        };

        try {
            const res = await api.post("/orders/", orderPayload);
            setLastOrder(res.data);
            setShowSuccess(true);
            resetForm();
            setTimeout(() => setShowSuccess(false), 5000);
        } catch (err: any) {
            const status = errorStatus(err);
            if (status !== null && isTerminalClientError(status)) {
                setErrorMessage(err.response?.data?.detail || "Order could not be accepted. Please review details.");
            } else {
                enqueueOrder(orderPayload);
                setQueueLength(getQueueLength());
                setQueuedMessage("Saved offline. Will sync to kitchen automatically.");
                setTimeout(() => setQueuedMessage(null), 4000);
                resetForm();
            }
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <div className="flex h-[calc(100vh-4rem)] overflow-hidden bg-stone-950 text-stone-100">
            {/* LEFT: Menu catalog & Search */}
            <div className="flex-1 flex flex-col border-r border-stone-800/80 overflow-hidden bg-stone-900/40">
                {/* Search & Utility Bar */}
                <div className="p-3 border-b border-stone-800/80 flex items-center gap-3 bg-stone-900/80">
                    <div className="relative flex-1">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-stone-400" />
                        <input
                            type="text"
                            placeholder="Search dishes or categories..."
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            className="w-full bg-stone-950 border border-stone-800 rounded-lg pl-9 pr-3 py-2 text-sm text-stone-100 placeholder-stone-500 focus:outline-none focus:border-amber-500/60"
                        />
                    </div>
                    {/* Till session button */}
                    <button
                        onClick={() => {
                            if (activeTill) handleFetchXReport();
                            setShowTillModal(true);
                        }}
                        className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium border transition-colors ${
                            activeTill
                                ? "bg-emerald-950/40 border-emerald-800/60 text-emerald-300"
                                : "bg-amber-950/40 border-amber-800/60 text-amber-300"
                        }`}
                    >
                        <DollarSign className="w-3.5 h-3.5" />
                        {activeTill ? "Till Open (X-Rep)" : "Open Till"}
                    </button>
                    {/* Parked tickets button */}
                    <button
                        onClick={() => setShowParkedModal(true)}
                        className="relative flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium border border-stone-700 bg-stone-800 text-stone-200 hover:bg-stone-700 transition-colors"
                    >
                        <PauseCircle className="w-3.5 h-3.5 text-amber-400" />
                        Parked
                        {parkedTickets.length > 0 && (
                            <span className="ml-1 px-1.5 py-0.5 rounded-full bg-amber-500 text-stone-950 text-[10px] font-bold">
                                {parkedTickets.length}
                            </span>
                        )}
                    </button>
                </div>

                {/* Categories Tab Strip */}
                <div className="flex gap-1.5 p-2 px-3 border-b border-stone-800/80 overflow-x-auto no-scrollbar bg-stone-900/30">
                    {categories.map((cat) => (
                        <button
                            key={cat}
                            onClick={() => setSelectedCategory(cat)}
                            className={`min-h-[44px] px-4 py-2 rounded-lg text-xs font-semibold whitespace-nowrap transition-all ${
                                selectedCategory === cat
                                    ? "bg-amber-500 text-stone-950 shadow-md shadow-amber-500/20"
                                    : "bg-stone-800/60 text-stone-400 hover:bg-stone-800 hover:text-stone-200"
                            }`}
                        >
                            {cat}
                        </button>
                    ))}
                </div>

                {/* Menu Items Grid */}
                <div className="flex-1 p-4 overflow-y-auto grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-3">
                    {loading ? (
                        <div className="col-span-full py-16 text-center text-stone-500 text-sm">
                            Loading catalog...
                        </div>
                    ) : filteredItems.length === 0 ? (
                        <div className="col-span-full py-16 text-center text-stone-500 text-sm">
                            No menu items match your search.
                        </div>
                    ) : (
                        filteredItems.map((item) => {
                            const isAvailable = item.is_available !== false;
                            const hasMods = item.modifier_groups && item.modifier_groups.length > 0;
                            return (
                                <div
                                    key={item.id}
                                    onClick={() => handleItemClick(item)}
                                    className={`relative p-3.5 rounded-xl border flex flex-col justify-between transition-all cursor-pointer select-none ${
                                        isAvailable
                                            ? "bg-stone-900/80 border-stone-800 hover:border-amber-500/50 hover:bg-stone-850 active:scale-[0.98]"
                                            : "bg-stone-950/60 border-red-900/30 opacity-60 cursor-not-allowed"
                                    }`}
                                >
                                    <div>
                                        <div className="flex items-start justify-between gap-1 mb-1">
                                            <h3 className="text-sm font-semibold text-stone-100 line-clamp-1">
                                                {item.name}
                                            </h3>
                                            <button
                                                title={isAvailable ? "Click to 86 item" : "Click to un-86 item"}
                                                onClick={(e) => toggle86(e, item)}
                                                className={`text-[10px] font-bold px-1.5 py-0.5 rounded border transition-colors ${
                                                    isAvailable
                                                        ? "bg-stone-800 text-stone-400 border-stone-700 hover:bg-red-950 hover:text-red-300"
                                                        : "bg-red-950 text-red-300 border-red-800"
                                                }`}
                                            >
                                                {isAvailable ? "86" : "86'd"}
                                            </button>
                                        </div>
                                        {item.description && (
                                            <p className="text-[11px] text-stone-400 line-clamp-2 mb-2">
                                                {item.description}
                                            </p>
                                        )}
                                    </div>
                                    <div className="flex items-center justify-between pt-2 border-t border-stone-800/60 mt-2">
                                        <span className="text-xs font-bold text-amber-400">
                                            {formatKES(item.price)}
                                        </span>
                                        {hasMods && (
                                            <span className="text-[10px] font-medium text-stone-400 bg-stone-800 px-1.5 py-0.5 rounded flex items-center gap-1">
                                                <Layers className="w-2.5 h-2.5" /> Options
                                            </span>
                                        )}
                                    </div>
                                </div>
                            );
                        })
                    )}
                </div>
            </div>

            {/* RIGHT: Active Order Cart & Ticket Actions */}
            <div className="w-96 lg:w-[420px] flex flex-col bg-stone-900 border-l border-stone-800/80 overflow-hidden">
                {/* Header: Operator Switcher & Offline Indicator */}
                <div className="p-3 border-b border-stone-800 flex items-center justify-between bg-stone-900/90">
                    <PinSwitcher
                        currentOperator={activeOperator}
                        onSwitch={switchOperator}
                    />
                    {queueLength > 0 && (
                        <div className="flex items-center gap-1 text-[11px] text-amber-400 bg-amber-950/60 border border-amber-800/60 px-2 py-1 rounded">
                            <CloudOff className="w-3 h-3" />
                            <span>{queueLength} queued</span>
                        </div>
                    )}
                </div>

                {/* Notifications & Error Alerts */}
                {errorMessage && (
                    <div className="p-2.5 bg-red-950/70 border-b border-red-800/80 text-xs text-red-200 flex items-center justify-between">
                        <span className="flex items-center gap-1.5">
                            <AlertTriangle className="w-3.5 h-3.5 text-red-400" />
                            {errorMessage}
                        </span>
                        <button onClick={() => setErrorMessage(null)} className="text-red-400 hover:text-red-200">
                            <X className="w-3.5 h-3.5" />
                        </button>
                    </div>
                )}
                {queuedMessage && (
                    <div className="p-2 bg-emerald-950/80 border-b border-emerald-800/80 text-xs text-emerald-200 flex items-center gap-1.5">
                        <Check className="w-3.5 h-3.5 text-emerald-400" />
                        {queuedMessage}
                    </div>
                )}
                {showSuccess && lastOrder && (
                    <div className="p-2.5 bg-emerald-950/90 border-b border-emerald-800 text-xs text-emerald-100 flex items-center justify-between">
                        <span>Order #{lastOrder.id} dispatched to Kitchen</span>
                        <button
                            onClick={() => setShowReceiptModal(true)}
                            className="flex items-center gap-1 text-[11px] font-bold bg-emerald-800 px-2 py-0.5 rounded text-white hover:bg-emerald-700"
                        >
                            <Printer className="w-3 h-3" /> Print
                        </button>
                    </div>
                )}

                {/* Order Metadata Form (Table, Channel, Order Type) */}
                <div className="p-3 border-b border-stone-800/80 grid grid-cols-3 gap-2 bg-stone-950/40">
                    <select
                        value={orderType}
                        onChange={(e) => setOrderType(e.target.value)}
                        className="bg-stone-900 border border-stone-800 rounded px-2 py-1.5 text-xs text-stone-200 focus:outline-none focus:border-amber-500/60"
                    >
                        <option value="dine_in">Dine In</option>
                        <option value="takeout">Takeout</option>
                        <option value="delivery">Delivery</option>
                    </select>

                    <select
                        value={deliveryChannel}
                        onChange={(e) => setDeliveryChannel(e.target.value)}
                        className="bg-stone-900 border border-stone-800 rounded px-2 py-1.5 text-xs text-stone-200 focus:outline-none focus:border-amber-500/60"
                    >
                        <option value="walk_in">Walk-in</option>
                        <option value="app">Online App</option>
                        <option value="uber_eats">Uber Eats</option>
                        <option value="glovo">Glovo</option>
                        <option value="bolt_food">Bolt Food</option>
                    </select>

                    <input
                        type="number"
                        placeholder="Table #"
                        value={tableNumber}
                        onChange={(e) => setTableNumber(e.target.value)}
                        className="bg-stone-900 border border-stone-800 rounded px-2 py-1.5 text-xs text-stone-200 placeholder-stone-500 focus:outline-none focus:border-amber-500/60"
                    />
                </div>

                {/* Cart Line Items */}
                <div className="flex-1 p-3 overflow-y-auto space-y-2">
                    {cart.length === 0 ? (
                        <div className="h-full flex flex-col items-center justify-center text-center p-6 text-stone-500">
                            <ShoppingBag className="w-10 h-10 mb-2 stroke-[1.2]" />
                            <p className="text-sm font-medium">Cart is empty</p>
                            <p className="text-xs text-stone-600 mt-1">Tap items on the left to add to ticket</p>
                        </div>
                    ) : (
                        cart.map((line) => {
                            const unitPrice = lineUnitPrice(line.menuItem, line.selectedModifiers);
                            return (
                                <div
                                    key={line.id}
                                    className="p-2.5 rounded-lg bg-stone-950/60 border border-stone-800/80 flex flex-col gap-1.5"
                                >
                                    <div className="flex items-start justify-between gap-2">
                                        <div className="flex-1">
                                            <h4 className="text-xs font-semibold text-stone-200">
                                                {line.menuItem.name}
                                            </h4>
                                            {line.selectedModifiers && line.selectedModifiers.length > 0 && (
                                                <div className="flex flex-wrap gap-1 mt-0.5">
                                                    {line.selectedModifiers.map((m, idx) => (
                                                        <span
                                                            key={idx}
                                                            className="text-[10px] bg-stone-800 text-stone-300 px-1 py-0.2 rounded"
                                                        >
                                                            +{m.name} ({formatKES(m.price_delta_cents)})
                                                        </span>
                                                    ))}
                                                </div>
                                            )}
                                            {line.notes && (
                                                <p className="text-[10px] text-amber-400/90 mt-0.5 italic">
                                                    Note: {line.notes}
                                                </p>
                                            )}
                                        </div>
                                        <span className="text-xs font-bold text-stone-100">
                                            {formatKES(unitPrice * line.quantity)}
                                        </span>
                                    </div>
                                    <div className="flex items-center justify-between pt-1 border-t border-stone-800/40">
                                        <span className="text-[11px] text-stone-500">
                                            {formatKES(unitPrice)} each
                                        </span>
                                        <div className="flex items-center gap-1.5">
                                            <button
                                                onClick={() => updateQtyPure(cart, line.id, -1).length === 0 ? setCart([]) : setCart((prev) => updateQtyPure(prev, line.id, -1))}
                                                className="w-6 h-6 rounded bg-stone-800 flex items-center justify-center text-stone-300 hover:bg-stone-700"
                                            >
                                                <Minus className="w-3 h-3" />
                                            </button>
                                            <span className="w-6 text-center text-xs font-bold text-stone-200">
                                                {line.quantity}
                                            </span>
                                            <button
                                                onClick={() => setCart((prev) => updateQtyPure(prev, line.id, 1))}
                                                className="w-6 h-6 rounded bg-stone-800 flex items-center justify-center text-stone-300 hover:bg-stone-700"
                                            >
                                                <Plus className="w-3 h-3" />
                                            </button>
                                            <button
                                                onClick={() => setCart((prev) => removeFromCartPure(prev, line.id))}
                                                className="w-6 h-6 rounded bg-stone-800/60 flex items-center justify-center text-red-400 hover:bg-red-950/60 ml-1"
                                            >
                                                <Trash2 className="w-3 h-3" />
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            );
                        })
                    )}
                </div>

                {/* Footer: Totals, Discounts, Payment & Dispatch */}
                <div className="p-3 border-t border-stone-800/80 bg-stone-950/80 flex flex-col gap-2.5">
                    {/* Subtotal & Discount rows */}
                    <div className="space-y-1 text-xs text-stone-400">
                        <div className="flex justify-between">
                            <span>Subtotal ({itemCount} items)</span>
                            <span className="text-stone-200">{formatKES(rawSubtotalCents)}</span>
                        </div>
                        {discountCents > 0 && (
                            <div className="flex justify-between text-emerald-400">
                                <span>Discount ({discountReason || "Applied"})</span>
                                <span>-{formatKES(discountCents)}</span>
                            </div>
                        )}
                        <div className="flex justify-between text-sm font-bold text-stone-100 pt-1 border-t border-stone-800/80">
                            <span>Total Due</span>
                            <span className="text-amber-400 text-base">{formatKES(finalTotalCents)}</span>
                        </div>
                    </div>

                    {/* Quick actions (Discount, Park, Notes) */}
                    <div className="grid grid-cols-3 gap-1.5">
                        <button
                            onClick={() => setShowDiscountModal(true)}
                            className="px-2 py-1.5 rounded bg-stone-800 hover:bg-stone-700 text-[11px] font-medium text-stone-300 flex items-center justify-center gap-1"
                        >
                            <Percent className="w-3 h-3 text-amber-400" />
                            {discountCents > 0 ? "Edit Disc" : "Discount"}
                        </button>
                        <button
                            onClick={parkCurrentTicket}
                            disabled={cart.length === 0}
                            className="px-2 py-1.5 rounded bg-stone-800 hover:bg-stone-700 disabled:opacity-40 text-[11px] font-medium text-stone-300 flex items-center justify-center gap-1"
                        >
                            <PauseCircle className="w-3 h-3 text-amber-400" /> Park
                        </button>
                        <button
                            onClick={() => setShowSplitModal(true)}
                            disabled={cart.length === 0}
                            className="px-2 py-1.5 rounded bg-stone-800 hover:bg-stone-700 disabled:opacity-40 text-[11px] font-medium text-stone-300 flex items-center justify-center gap-1"
                        >
                            <CreditCard className="w-3 h-3 text-emerald-400" /> Split Pay
                        </button>
                    </div>

                    {/* Primary Submit Button */}
                    <div className="flex gap-2">
                        <button
                            onClick={() => handleSubmitOrder()}
                            disabled={cart.length === 0 || submitting}
                            className="flex-1 py-3 rounded-xl font-bold text-sm bg-amber-500 text-stone-950 hover:bg-amber-400 disabled:opacity-40 active:scale-[0.99] transition-all flex items-center justify-center gap-2 shadow-lg shadow-amber-500/20"
                        >
                            {submitting ? (
                                <RefreshCw className="w-4 h-4 animate-spin" />
                            ) : (
                                <>
                                    <UtensilsCrossed className="w-4 h-4" />
                                    Send to Kitchen ({formatKES(finalTotalCents)})
                                </>
                            )}
                        </button>
                    </div>
                </div>
            </div>

            {/* MODIFIERS DIALOG */}
            {modifierItem && (
                <div className="fixed inset-0 bg-stone-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-stone-900 border border-stone-800 rounded-2xl max-w-md w-full p-5 flex flex-col gap-4">
                        <div className="flex items-start justify-between">
                            <div>
                                <h3 className="text-base font-bold text-stone-100">{modifierItem.name}</h3>
                                <p className="text-xs text-stone-400">{formatKES(modifierItem.price)} base price</p>
                            </div>
                            <button onClick={() => setModifierItem(null)} className="text-stone-400 hover:text-stone-200">
                                <X className="w-5 h-5" />
                            </button>
                        </div>

                        {/* Modifier groups */}
                        <div className="space-y-3 max-h-60 overflow-y-auto">
                            {(modifierItem.modifier_groups || []).map((group) => (
                                <div key={group.id} className="space-y-1.5">
                                    <span className="text-xs font-semibold text-stone-300 block">{group.name}</span>
                                    <div className="grid grid-cols-2 gap-1.5">
                                        {group.options.map((opt) => {
                                            const isSelected = selectedMods.some((m) => m.name === opt.name);
                                            return (
                                                <button
                                                    key={opt.id || opt.name}
                                                    type="button"
                                                    onClick={() => {
                                                        if (isSelected) {
                                                            setSelectedMods((prev) => prev.filter((m) => m.name !== opt.name));
                                                        } else {
                                                            setSelectedMods((prev) => [...prev, opt]);
                                                        }
                                                    }}
                                                    className={`px-2.5 py-2 rounded-lg text-xs font-medium border flex items-center justify-between transition-all ${
                                                        isSelected
                                                            ? "bg-amber-500/20 border-amber-500 text-amber-200"
                                                            : "bg-stone-950/60 border-stone-800 text-stone-300 hover:border-stone-700"
                                                    }`}
                                                >
                                                    <span>{opt.name}</span>
                                                    <span className="text-[10px] text-stone-400 font-mono">
                                                        +{formatKES(opt.price_delta_cents)}
                                                    </span>
                                                </button>
                                            );
                                        })}
                                    </div>
                                </div>
                            ))}
                            {/* Line notes */}
                            <div className="space-y-1 pt-2">
                                <label className="text-xs font-semibold text-stone-300">Special Instructions / Allergens</label>
                                <input
                                    type="text"
                                    placeholder="e.g. No onion, allergy to peanuts"
                                    value={itemLineNote}
                                    onChange={(e) => setItemLineNote(e.target.value)}
                                    className="w-full bg-stone-950 border border-stone-800 rounded-lg px-3 py-2 text-xs text-stone-100 placeholder-stone-500 focus:outline-none focus:border-amber-500/60"
                                />
                            </div>
                        </div>

                        <div className="flex gap-2 pt-2 border-t border-stone-800">
                            <button
                                onClick={() => setModifierItem(null)}
                                className="flex-1 py-2.5 rounded-xl border border-stone-700 text-xs font-semibold text-stone-300 hover:bg-stone-800"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={confirmModifierItem}
                                className="flex-1 py-2.5 rounded-xl bg-amber-500 text-stone-950 text-xs font-bold hover:bg-amber-400"
                            >
                                Add to Ticket
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* DISCOUNT DIALOG */}
            {showDiscountModal && (
                <div className="fixed inset-0 bg-stone-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-stone-900 border border-stone-800 rounded-2xl max-w-sm w-full p-5 flex flex-col gap-4">
                        <h3 className="text-sm font-bold text-stone-100">Apply Discount / Comp</h3>
                        <div className="flex gap-2">
                            <button
                                onClick={() => setDiscountType("percent")}
                                className={`flex-1 py-2 rounded-lg text-xs font-semibold border ${
                                    discountType === "percent"
                                        ? "bg-amber-500/20 border-amber-500 text-amber-300"
                                        : "bg-stone-950 border-stone-800 text-stone-400"
                                }`}
                            >
                                Percentage (%)
                            </button>
                            <button
                                onClick={() => setDiscountType("amount")}
                                className={`flex-1 py-2 rounded-lg text-xs font-semibold border ${
                                    discountType === "amount"
                                        ? "bg-amber-500/20 border-amber-500 text-amber-300"
                                        : "bg-stone-950 border-stone-800 text-stone-400"
                                }`}
                            >
                                KES Amount
                            </button>
                        </div>
                        <div>
                            <label className="text-xs text-stone-400 block mb-1">
                                {discountType === "percent" ? "Discount Percentage (%)" : "Discount Amount (KES)"}
                            </label>
                            <input
                                type="number"
                                min={0}
                                max={discountType === "percent" ? 100 : undefined}
                                value={discountValue || ""}
                                onChange={(e) => setDiscountValue(Number(e.target.value))}
                                className="w-full bg-stone-950 border border-stone-800 rounded-lg px-3 py-2 text-sm text-stone-100 focus:outline-none focus:border-amber-500/60"
                            />
                        </div>
                        <div>
                            <label className="text-xs text-stone-400 block mb-1">Reason (Required for audit)</label>
                            <input
                                type="text"
                                placeholder="e.g. Staff meal, VIP, Spillage compensation"
                                value={discountReason}
                                onChange={(e) => setDiscountReason(e.target.value)}
                                className="w-full bg-stone-950 border border-stone-800 rounded-lg px-3 py-2 text-xs text-stone-100 placeholder-stone-500 focus:outline-none focus:border-amber-500/60"
                            />
                        </div>
                        <div className="flex gap-2 pt-2 border-t border-stone-800">
                            <button
                                onClick={() => {
                                    setDiscountValue(0);
                                    setDiscountReason("");
                                    setShowDiscountModal(false);
                                }}
                                className="flex-1 py-2 rounded-xl border border-stone-700 text-xs text-stone-400 hover:bg-stone-800"
                            >
                                Remove
                            </button>
                            <button
                                onClick={() => setShowDiscountModal(false)}
                                className="flex-1 py-2 rounded-xl bg-amber-500 text-stone-950 text-xs font-bold hover:bg-amber-400"
                            >
                                Apply
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* SPLIT PAYMENT DIALOG */}
            {showSplitModal && (
                <div className="fixed inset-0 bg-stone-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-stone-900 border border-stone-800 rounded-2xl max-w-md w-full p-5 flex flex-col gap-4">
                        <div className="flex items-center justify-between">
                            <h3 className="text-sm font-bold text-stone-100">Split Tender Payment</h3>
                            <button onClick={() => setShowSplitModal(false)} className="text-stone-400 hover:text-stone-200">
                                <X className="w-5 h-5" />
                            </button>
                        </div>

                        <div className="p-3 bg-stone-950 rounded-xl border border-stone-800/80 flex justify-between items-center text-xs">
                            <span className="text-stone-400">Total Due:</span>
                            <span className="text-base font-bold text-amber-400">{formatKES(finalTotalCents)}</span>
                        </div>

                        <div className="space-y-2">
                            {splitPayments.map((p, idx) => (
                                <div key={p.method} className="p-2.5 bg-stone-950/60 rounded-lg border border-stone-800/80 flex items-center gap-2">
                                    <span className="w-20 text-xs font-semibold capitalize text-stone-300">
                                        {p.method}
                                    </span>
                                    <input
                                        type="number"
                                        placeholder="0 KES"
                                        value={p.amountKES || ""}
                                        onChange={(e) => {
                                            const val = Number(e.target.value);
                                            setSplitPayments((prev) =>
                                                prev.map((item, i) => (i === idx ? { ...item, amountKES: val } : item))
                                            );
                                        }}
                                        className="flex-1 bg-stone-900 border border-stone-800 rounded px-2.5 py-1.5 text-xs text-stone-100"
                                    />
                                    {p.method === "mpesa" && (
                                        <input
                                            type="text"
                                            placeholder="Receipt code"
                                            value={p.reference}
                                            onChange={(e) => {
                                                const code = e.target.value;
                                                setSplitPayments((prev) =>
                                                    prev.map((item, i) => (i === idx ? { ...item, reference: code } : item))
                                                );
                                            }}
                                            className="w-24 bg-stone-900 border border-stone-800 rounded px-2 py-1.5 text-[11px] text-stone-200"
                                        />
                                    )}
                                </div>
                            ))}
                        </div>

                        <div className="flex justify-between text-xs pt-2 border-t border-stone-800">
                            <span className="text-stone-400">Paid Total:</span>
                            <span className="font-bold text-stone-200">
                                {formatKES(splitPayments.reduce((sum, p) => sum + (p.amountKES * 100), 0))}
                            </span>
                        </div>

                        <button
                            onClick={() => handleSubmitOrder(splitPayments)}
                            disabled={submitting}
                            className="w-full py-3 rounded-xl bg-emerald-500 text-stone-950 font-bold text-xs hover:bg-emerald-400"
                        >
                            Confirm Split Payment & Dispatch
                        </button>
                    </div>
                </div>
            )}

            {/* TILL SESSIONS MODAL */}
            {showTillModal && (
                <div className="fixed inset-0 bg-stone-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-stone-900 border border-stone-800 rounded-2xl max-w-md w-full p-5 flex flex-col gap-4">
                        <div className="flex items-center justify-between">
                            <h3 className="text-sm font-bold text-stone-100">Till & Cash Drawer Management</h3>
                            <button onClick={() => setShowTillModal(false)} className="text-stone-400 hover:text-stone-200">
                                <X className="w-5 h-5" />
                            </button>
                        </div>

                        {!activeTill ? (
                            <div className="space-y-3">
                                <p className="text-xs text-stone-400">
                                    No till session currently open. Open a new drawer with opening cash float.
                                </p>
                                <div>
                                    <label className="text-xs text-stone-300 block mb-1">Opening Cash Float (KES)</label>
                                    <input
                                        type="number"
                                        value={openingFloat}
                                        onChange={(e) => setOpeningFloat(Number(e.target.value))}
                                        className="w-full bg-stone-950 border border-stone-800 rounded-lg px-3 py-2 text-sm text-stone-100 focus:outline-none focus:border-amber-500/60"
                                    />
                                </div>
                                <button
                                    onClick={handleOpenTill}
                                    className="w-full py-2.5 rounded-xl bg-emerald-500 text-stone-950 font-bold text-xs hover:bg-emerald-400"
                                >
                                    Open Till Session
                                </button>
                            </div>
                        ) : (
                            <div className="space-y-3">
                                {tillXReport && (
                                    <div className="p-3 bg-stone-950 rounded-xl border border-stone-800/80 space-y-1.5 text-xs text-stone-300">
                                        <div className="flex justify-between font-bold text-amber-400 pb-1 border-b border-stone-800">
                                            <span>Shift X-Report</span>
                                            <span>{tillXReport.order_count} Orders</span>
                                        </div>
                                        <div className="flex justify-between">
                                            <span>Opening Float:</span>
                                            <span>{formatKES(tillXReport.opening_float_cents)}</span>
                                        </div>
                                        <div className="flex justify-between">
                                            <span>Cash Sales:</span>
                                            <span>{formatKES(tillXReport.cash_sales_cents)}</span>
                                        </div>
                                        <div className="flex justify-between">
                                            <span>M-Pesa Sales:</span>
                                            <span>{formatKES(tillXReport.mpesa_sales_cents)}</span>
                                        </div>
                                        <div className="flex justify-between">
                                            <span>Card Sales:</span>
                                            <span>{formatKES(tillXReport.card_sales_cents)}</span>
                                        </div>
                                        <div className="flex justify-between font-bold text-stone-100 pt-1 border-t border-stone-800">
                                            <span>Expected Cash in Drawer:</span>
                                            <span>{formatKES(tillXReport.expected_cash_cents)}</span>
                                        </div>
                                    </div>
                                )}

                                <div>
                                    <label className="text-xs text-stone-300 block mb-1">Closing Counted Cash (KES)</label>
                                    <input
                                        type="number"
                                        value={closingCashCount || ""}
                                        onChange={(e) => setClosingCashCount(Number(e.target.value))}
                                        placeholder="Enter actual counted notes & coins"
                                        className="w-full bg-stone-950 border border-stone-800 rounded-lg px-3 py-2 text-sm text-stone-100"
                                    />
                                </div>
                                <div>
                                    <label className="text-xs text-stone-300 block mb-1">Variance Reason (if discrepancy)</label>
                                    <input
                                        type="text"
                                        value={varianceReason}
                                        onChange={(e) => setVarianceReason(e.target.value)}
                                        placeholder="e.g. Bank run deposit / change shortage"
                                        className="w-full bg-stone-950 border border-stone-800 rounded-lg px-3 py-2 text-xs text-stone-100"
                                    />
                                </div>

                                <div className="flex gap-2 pt-2 border-t border-stone-800">
                                    <button
                                        onClick={handleCloseTill}
                                        className="w-full py-2.5 rounded-xl bg-red-600 text-white font-bold text-xs hover:bg-red-500"
                                    >
                                        Close Till & Print Z-Report
                                    </button>
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* PARKED TICKETS MODAL */}
            {showParkedModal && (
                <div className="fixed inset-0 bg-stone-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-stone-900 border border-stone-800 rounded-2xl max-w-md w-full p-5 flex flex-col gap-4">
                        <div className="flex items-center justify-between">
                            <h3 className="text-sm font-bold text-stone-100">Held / Parked Tickets</h3>
                            <button onClick={() => setShowParkedModal(false)} className="text-stone-400 hover:text-stone-200">
                                <X className="w-5 h-5" />
                            </button>
                        </div>
                        <div className="space-y-2 max-h-72 overflow-y-auto">
                            {parkedTickets.length === 0 ? (
                                <p className="text-center text-xs text-stone-500 py-6">No tickets currently held.</p>
                            ) : (
                                parkedTickets.map((t) => (
                                    <div
                                        key={t.id}
                                        className="p-3 bg-stone-950 rounded-xl border border-stone-800 flex items-center justify-between"
                                    >
                                        <div>
                                            <span className="text-xs font-bold text-stone-200">{t.label}</span>
                                            <p className="text-[10px] text-stone-400">
                                                {t.cart.length} items &bull; Parked at {t.parkedAt}
                                            </p>
                                        </div>
                                        <button
                                            onClick={() => recallParkedTicket(t)}
                                            className="px-3 py-1.5 rounded-lg bg-amber-500 text-stone-950 text-xs font-bold hover:bg-amber-400"
                                        >
                                            Recall
                                        </button>
                                    </div>
                                ))
                            )}
                        </div>
                    </div>
                </div>
            )}

            {/* RECEIPT PRINT MODAL */}
            {showReceiptModal && lastOrder && (
                <div className="fixed inset-0 bg-stone-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-stone-900 border border-stone-800 rounded-2xl max-w-sm w-full p-5 flex flex-col gap-4">
                        <div className="flex items-center justify-between border-b border-stone-800 pb-2">
                            <h3 className="text-xs font-bold text-stone-300">Receipt Preview</h3>
                            <button onClick={() => setShowReceiptModal(false)} className="text-stone-400 hover:text-stone-200">
                                <X className="w-4 h-4" />
                            </button>
                        </div>
                        {/* Printable stub */}
                        <div className="bg-white text-black p-4 rounded-lg font-mono text-xs space-y-2 shadow-inner">
                            <div className="text-center font-bold text-sm">CHAKULA RESTAURANT</div>
                            <div className="text-center text-[10px] text-gray-600">Nairobi, Kenya</div>
                            <div className="border-b border-dashed border-gray-400 my-1" />
                            <div className="flex justify-between">
                                <span>Order #{lastOrder.id}</span>
                                <span>{new Date(lastOrder.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
                            </div>
                            {lastOrder.table_number && <div>Table: {lastOrder.table_number}</div>}
                            <div className="border-b border-dashed border-gray-400 my-1" />
                            <div className="space-y-1">
                                {(lastOrder.items || []).map((it: any) => (
                                    <div key={it.id} className="flex justify-between">
                                        <span>{it.quantity}x {it.item_name}</span>
                                        <span>{formatKES(it.unit_price * it.quantity)}</span>
                                    </div>
                                ))}
                            </div>
                            <div className="border-b border-dashed border-gray-400 my-1" />
                            <div className="flex justify-between font-bold text-sm">
                                <span>TOTAL:</span>
                                <span>{formatKES(lastOrder.total)}</span>
                            </div>
                            <div className="text-center text-[10px] text-gray-500 pt-2">
                                Thank you for dining with us!
                            </div>
                        </div>
                        <button
                            onClick={() => {
                                window.print();
                                setShowReceiptModal(false);
                            }}
                            className="w-full py-2.5 rounded-xl bg-amber-500 text-stone-950 font-bold text-xs hover:bg-amber-400 flex items-center justify-center gap-1.5"
                        >
                            <Printer className="w-3.5 h-3.5" /> Print Receipt
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
}
