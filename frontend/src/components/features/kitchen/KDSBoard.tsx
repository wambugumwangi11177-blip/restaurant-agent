"use client";

import { useEffect, useState, useCallback } from "react";
import api from "@/lib/api";
import {
    ChefHat,
    CheckCircle2,
    RefreshCw,
    Bell,
    Truck,
    UtensilsCrossed,
    ShoppingBag,
    LayoutGrid,
} from "lucide-react";
import KDSColumn from "./KDSColumn";
import { useToast } from "@/components/ui/Toast";
import { getErrorMessage } from "@/lib/errors";

export interface OrderItem {
    id: number;
    menu_item_id: number;
    quantity: number;
    unit_price: number;
    item_name: string;
    prep_station: string;
}

const STATIONS = [
    { v: "all", label: "All" },
    { v: "grill", label: "Grill" },
    { v: "fryer", label: "Fryer" },
    { v: "salad", label: "Salad" },
    { v: "drinks", label: "Drinks" },
    { v: "main", label: "Main" },
];

export interface Order {
    id: number;
    status: string;
    order_type: string;
    delivery_channel: string;
    customer_name: string;
    table_number: number | null;
    total: number;
    notes: string;
    created_at: string;
    items: OrderItem[];
}

/**
 * The kitchen display board (KDS) — extracted from the original
 * dashboard/kitchen/page.tsx so every tier with `kitchen` access (Owner,
 * Manager, Supervisor, Kitchen RW; Waiter R) can reuse the exact same
 * component. `readOnly` hides the status-advance button — used for Waiter,
 * who can see the board (directive 015: `kitchen` = R for Waiter) but
 * shouldn't be the one moving orders through it.
 */
export default function KDSBoard({ readOnly = false }: { readOnly?: boolean }) {
    const [orders, setOrders] = useState<Order[]>([]);
    const [loading, setLoading] = useState(true);
    const [updating, setUpdating] = useState<number | null>(null);
    const [rejectingId, setRejectingId] = useState<number | null>(null);
    const [rejectReason, setRejectReason] = useState("");
    const [notingId, setNotingId] = useState<number | null>(null);
    const [noteText, setNoteText] = useState("");
    const [stationFilter, setStationFilter] = useState("all");
    const [incidentId, setIncidentId] = useState<number | null>(null);
    const [incidentType, setIncidentType] = useState<"remake" | "quality_issue">("remake");
    const [incidentReason, setIncidentReason] = useState("");
    const [now, setNow] = useState(() => Date.now());
    const { showToast, toastNode } = useToast();

    const fetchOrders = useCallback(async () => {
        try {
            const res = await api.get("/orders/active");
            setOrders(res.data);
        } catch {
            // Silently retry
        }
        setLoading(false);
        setNow(Date.now());
    }, []);

    useEffect(() => {
        fetchOrders();
        const interval = setInterval(fetchOrders, 10000); // Refresh every 10s
        return () => clearInterval(interval);
    }, [fetchOrders]);

    const moveOrder = async (orderId: number, newStatus: string) => {
        setUpdating(orderId);
        try {
            await api.post(`/orders/${orderId}/status`, { status: newStatus });
            await fetchOrders();
        } catch (err) {
            showToast(getErrorMessage(err, "Failed to update order"), "error");
        }
        setUpdating(null);
    };

    const rejectOrder = async (orderId: number) => {
        setUpdating(orderId);
        try {
            if (rejectReason.trim()) {
                const order = orders.find((o) => o.id === orderId);
                const note = `Rejected: ${rejectReason.trim()}`;
                await api.post(`/orders/${orderId}/details`, {
                    notes: order?.notes ? `${order.notes} | ${note}` : note,
                });
            }
            await api.post(`/orders/${orderId}/status`, { status: "cancelled" });
            setRejectingId(null);
            setRejectReason("");
            await fetchOrders();
        } catch (err) {
            showToast(getErrorMessage(err, "Failed to reject order"), "error");
        }
        setUpdating(null);
    };

    const addNote = async (orderId: number) => {
        if (!noteText.trim()) return;
        setUpdating(orderId);
        try {
            const order = orders.find((o) => o.id === orderId);
            const combined = order?.notes ? `${order.notes} | ${noteText.trim()}` : noteText.trim();
            await api.post(`/orders/${orderId}/details`, { notes: combined });
            setNotingId(null);
            setNoteText("");
            await fetchOrders();
        } catch (err) {
            showToast(getErrorMessage(err, "Failed to add note"), "error");
        }
        setUpdating(null);
    };

    const logIncident = async (orderId: number) => {
        setUpdating(orderId);
        try {
            await api.post("/orders/incidents", {
                order_id: orderId,
                incident_type: incidentType,
                reason: incidentReason,
            });
            setIncidentId(null);
            setIncidentReason("");
            await fetchOrders();
        } catch (err) {
            showToast(getErrorMessage(err, "Failed to log incident"), "error");
        }
        setUpdating(null);
    };

    // Station filter: an order stays visible if any of its items belong to
    // the selected station; within a visible order, only that station's
    // items are shown (so the grill screen doesn't show drinks). "All"
    // shows every item as before.
    const itemsForStation = (order: Order) =>
        stationFilter === "all" ? order.items : order.items.filter((i) => i.prep_station === stationFilter);
    const matchesStation = (order: Order) => itemsForStation(order).length > 0;

    const filteredOrders = orders.filter(matchesStation).map((o) => ({ ...o, items: itemsForStation(o) }));

    const pending = filteredOrders.filter((o) => o.status === "pending");
    const cooking = filteredOrders.filter((o) => o.status === "prep");
    const ready = filteredOrders.filter((o) => o.status === "ready");

    const minutesAgo = (dateStr: string) => {
        const diff = Date.now() - new Date(dateStr).getTime();
        const mins = Math.floor(diff / 60000);
        if (mins < 1) return "Just now";
        if (mins === 1) return "1 min ago";
        return `${mins} mins ago`;
    };

    const orderTypeIcon = (type: string) => {
        if (type === "delivery") return Truck;
        if (type === "takeout") return ShoppingBag;
        return UtensilsCrossed;
    };

    const channelLabel = (ch: string) => {
        const map: Record<string, string> = {
            uber_eats: "Uber Eats",
            bolt_food: "Bolt Food",
            glovo: "Glovo",
            walk_in: "",
            app: "App Order",
        };
        return map[ch] || "";
    };

    if (loading) {
        return (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 h-[calc(100vh-120px)]">
                {[...Array(3)].map((_, i) => (
                    <div key={i} className="bg-surface rounded-xl animate-pulse" />
                ))}
            </div>
        );
    }

    return (
        <div className="flex flex-col h-[calc(100vh-120px)]">
            {toastNode}
            {/* Header */}
            <div className="flex items-center justify-between mb-4">
                <div>
                    <h1 className="text-xl font-bold text-text">Kitchen</h1>
                    <p className="text-xs text-text-dim">
                        {orders.length > 0
                            ? `${orders.length} order${orders.length > 1 ? "s" : ""} right now`
                            : "No orders right now — take a breather"}
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    <div className="hidden sm:flex items-center gap-1 bg-surface-hover border border-border rounded-lg p-0.5">
                        <LayoutGrid className="w-3 h-3 text-text-dim ml-1.5" />
                        {STATIONS.map((s) => (
                            <button
                                key={s.v}
                                onClick={() => setStationFilter(s.v)}
                                className={`px-2 py-1 rounded text-[10px] font-medium transition-all ${stationFilter === s.v
                                    ? "bg-accent text-black"
                                    : "text-text-muted hover:text-text"
                                    }`}
                            >
                                {s.label}
                            </button>
                        ))}
                    </div>
                    <button
                        onClick={fetchOrders}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-surface-hover border border-border rounded-lg text-xs text-text-muted hover:text-text transition-all"
                    >
                        <RefreshCw className="w-3 h-3" />
                        Refresh
                    </button>
                </div>
            </div>

            {/* Three-column board */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 flex-1 min-h-0">
                {/* Incoming */}
                <KDSColumn
                    title="Incoming"
                    subtitle="New orders"
                    count={pending.length}
                    color="var(--warning)"
                    icon={Bell}
                    orders={pending}
                    now={now}
                    actionLabel="Start Cooking"
                    actionStatus="prep"
                    onAction={moveOrder}
                    updating={updating}
                    minutesAgo={minutesAgo}
                    orderTypeIcon={orderTypeIcon}
                    channelLabel={channelLabel}
                    readOnly={readOnly}
                    allowReject
                    rejectingId={rejectingId}
                    setRejectingId={setRejectingId}
                    rejectReason={rejectReason}
                    setRejectReason={setRejectReason}
                    onReject={rejectOrder}
                    notingId={notingId}
                    setNotingId={setNotingId}
                    noteText={noteText}
                    setNoteText={setNoteText}
                    onAddNote={addNote}
                    incidentId={incidentId}
                    setIncidentId={setIncidentId}
                    incidentType={incidentType}
                    setIncidentType={setIncidentType}
                    incidentReason={incidentReason}
                    setIncidentReason={setIncidentReason}
                    onLogIncident={logIncident}
                />

                {/* Cooking */}
                <KDSColumn
                    title="Cooking"
                    subtitle="Being prepared"
                    count={cooking.length}
                    color="var(--accent)"
                    icon={ChefHat}
                    orders={cooking}
                    now={now}
                    actionLabel="Ready"
                    actionStatus="ready"
                    onAction={moveOrder}
                    updating={updating}
                    minutesAgo={minutesAgo}
                    orderTypeIcon={orderTypeIcon}
                    channelLabel={channelLabel}
                    readOnly={readOnly}
                    notingId={notingId}
                    setNotingId={setNotingId}
                    noteText={noteText}
                    setNoteText={setNoteText}
                    onAddNote={addNote}
                    incidentId={incidentId}
                    setIncidentId={setIncidentId}
                    incidentType={incidentType}
                    setIncidentType={setIncidentType}
                    incidentReason={incidentReason}
                    setIncidentReason={setIncidentReason}
                    onLogIncident={logIncident}
                />

                {/* Ready */}
                <KDSColumn
                    title="Ready"
                    subtitle="Waiting for pickup"
                    count={ready.length}
                    color="var(--success)"
                    icon={CheckCircle2}
                    orders={ready}
                    now={now}
                    actionLabel="Served"
                    actionStatus="served"
                    onAction={moveOrder}
                    notingId={notingId}
                    setNotingId={setNotingId}
                    noteText={noteText}
                    setNoteText={setNoteText}
                    onAddNote={addNote}
                    incidentId={incidentId}
                    setIncidentId={setIncidentId}
                    incidentType={incidentType}
                    setIncidentType={setIncidentType}
                    incidentReason={incidentReason}
                    setIncidentReason={setIncidentReason}
                    onLogIncident={logIncident}
                    updating={updating}
                    minutesAgo={minutesAgo}
                    orderTypeIcon={orderTypeIcon}
                    channelLabel={channelLabel}
                    readOnly={readOnly}
                />
            </div>
        </div>
    );
}
