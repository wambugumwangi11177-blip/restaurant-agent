"use client";

import {useDailyReview} from "@/lib/owner/useDailyReview";
import Link from "next/link";
import {useListQuery} from "@/lib/owner/useListQuery";
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
    const reviewDay=useDailyReview();
    const [tool]=useListQuery("tool");
    const titles:Record<string,string>={approval:"Approve purchase orders",history:"Purchase history",orders:"Purchase orders", "par-levels":"Par levels", "supplier-records":"Supplier records"};
    const [suppliers, setSuppliers] = useState<Supplier[] | null>(null);
    const [items, setItems] = useState<PurchasingItem[]>([]);
    const [orders, setOrders] = useState<PurchaseOrder[] | null>(null);
    const [loading, setLoading] = useState(true);
    const [loadError,setLoadError]=useState(false);
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
            setForbidden(false);setLoadError(false);
        } catch (err) {
            if (isHttpStatus(err, 403)) setForbidden(true); else setLoadError(true);
        }
        setLoading(false);
    };

    useEffect(() => { fetchAll(); }, [reviewDay]);

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
                    Purchasing is only available to Owners, Managers, Accountants, Supervisors, and Stockkeepers.
                </p>
            </div>
        );
    }

    return (
        <div className="space-y-5">
            {toastNode}
            {loadError&&<p role="alert">Could not read purchasing records. <button onClick={()=>void fetchAll()} className="underline min-h-11">Retry</button></p>}

            <div>
                <Link href="/explore?area=store" className="inline-flex min-h-11 underline">← Store tools</Link><h1 className="text-xl font-bold text-text">{titles[tool]??"Choose a purchasing tool"}</h1>
                <p className="text-sm text-text-dim mt-0.5">
                    Automated reordering — draft orders are prepared for you; nothing reaches a supplier without approval.
                </p>
            </div>

            {!tool&&<div className="grid gap-3">{Object.entries(titles).filter(([id])=>id!=="orders").map(([id,title])=><Link key={id} href={`/purchasing?tool=${id}`} className="rounded-xl border p-4">{title} →</Link>)}</div>}
            {tool==="approval"&&!(orders||[]).some(o=>o.status==="PENDING")&&<p>No purchase orders are awaiting approval.</p>}
            {tool==="history"&&!(orders||[]).some(o=>!["PENDING","SENT"].includes(o.status))&&<p>No completed purchase history recorded.</p>}
            {["approval","history","orders"].includes(tool)&&<PurchaseOrdersPanel
                orders={(orders || []).filter(o=>tool==="approval"?o.status==="PENDING":tool==="history"?!["PENDING","SENT"].includes(o.status):true)}
                submitting={submitting}
                setSubmitting={setSubmitting}
                showToast={showToast}
                fetchAll={fetchAll}
            />}

            {tool==="par-levels"&&<section aria-label="Par levels" className="rounded-xl border p-4"><ReorderSettingsPanel
                items={items}
                suppliers={suppliers}
                submitting={submitting}
                setSubmitting={setSubmitting}
                showToast={showToast}
                fetchAll={fetchAll}
            /></section>}

            {tool==="supplier-records"&&<section aria-label="Supplier records" className="rounded-xl border p-4"><SupplierPanel
                suppliers={suppliers}
                submitting={submitting}
                setSubmitting={setSubmitting}
                showToast={showToast}
                fetchAll={fetchAll}
            /></section>}
        </div>
    );
}
