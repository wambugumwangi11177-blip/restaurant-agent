"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { ShieldAlert } from "lucide-react";
import { useToast } from "@/components/ui/Toast";
import { isHttpStatus } from "@/lib/errors";
import PurchaseOrdersPanel from "./PurchaseOrdersPanel";
import ReorderSettingsPanel from "./ReorderSettingsPanel";
import SupplierPanel from "./SupplierPanel";
import type { PurchasingItem, Supplier, PurchaseOrder } from "./types";

/**
 * Purchasing/supplier workspace — extracted from the original
 * dashboard/purchasing/page.tsx unmodified. Already self-gates: the backend
 * differentiates approve (Manager/Supervisor) vs receive (Manager/
 * Stockkeeper) vs read (Manager/Controller/Stockkeeper/Supervisor/Owner), and
 * a role outside all of those gets the existing 403 -> "forbidden" screen.
 * Reused as-is across every tier with `purchasing` access.
 *
 * Split into PurchaseOrdersPanel (approve/receive/history),
 * ReorderSettingsPanel (par level + default supplier per item), and
 * SupplierPanel (add/edit suppliers) — each owns its own local UI state and
 * calls back into fetchAll()/showToast() here to keep data + toast in sync.
 */
export default function PurchasingWorkspace() {
    const [suppliers, setSuppliers] = useState<Supplier[] | null>(null);
    const [items, setItems] = useState<PurchasingItem[]>([]);
    const [orders, setOrders] = useState<PurchaseOrder[] | null>(null);
    const [loading, setLoading] = useState(true);
    const [forbidden, setForbidden] = useState(false);
    const [submitting, setSubmitting] = useState(false);
    const { showToast, toastNode } = useToast();

    const fetchAll = async () => {
        try {
            const [suppliersRes, itemsRes, ordersRes] = await Promise.all([
                api.get("/suppliers/"),
                api.get("/inventory/"),
                api.get("/purchase-orders/"),
            ]);
            setSuppliers(suppliersRes.data);
            setItems(Array.isArray(itemsRes.data) ? itemsRes.data : []);
            setOrders(ordersRes.data);
            setForbidden(false);
        } catch (err) {
            if (isHttpStatus(err, 403)) setForbidden(true);
        }
        setLoading(false);
    };

    useEffect(() => { fetchAll(); }, []);

    if (loading) {
        return (
            <div className="space-y-3">
                {[...Array(3)].map((_, i) => (
                    <div key={i} className="bg-surface rounded-xl h-14 animate-pulse" />
                ))}
            </div>
        );
    }

    if (forbidden) {
        return (
            <div className="flex flex-col items-center justify-center min-h-[40vh] space-y-3 text-center">
                <ShieldAlert className="w-8 h-8 text-text-dim" />
                <p className="text-sm text-text-muted">
                    Purchasing is only available to Owners, Managers, Controllers, Supervisors, and Stockkeepers.
                </p>
            </div>
        );
    }

    return (
        <div className="space-y-5">
            {toastNode}

            <div>
                <h1 className="text-xl font-bold text-text">Purchasing</h1>
                <p className="text-sm text-text-dim mt-0.5">
                    Automated reordering — draft orders are prepared for you; nothing reaches a supplier without approval.
                </p>
            </div>

            <PurchaseOrdersPanel
                orders={orders || []}
                submitting={submitting}
                setSubmitting={setSubmitting}
                showToast={showToast}
                fetchAll={fetchAll}
            />

            <ReorderSettingsPanel
                items={items}
                suppliers={suppliers}
                submitting={submitting}
                setSubmitting={setSubmitting}
                showToast={showToast}
                fetchAll={fetchAll}
            />

            <SupplierPanel
                suppliers={suppliers}
                submitting={submitting}
                setSubmitting={setSubmitting}
                showToast={showToast}
                fetchAll={fetchAll}
            />
        </div>
    );
}
