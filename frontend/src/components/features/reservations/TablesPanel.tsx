"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Brush } from "lucide-react";
import FormField from "@/components/ui/FormField";

interface FloorTable {
    id: number;
    table_number: number;
    capacity: number;
    status: string;
}

interface TablesPanelProps {
    visible: boolean;
    floorTables: FloorTable[];
    newTableNumber: string;
    onNewTableNumberChange: (v: string) => void;
    newTableCapacity: string;
    onNewTableCapacityChange: (v: string) => void;
    submitting: boolean;
    onAddTable: () => void;
    onTableStatus: (tableId: number, status: string) => void;
}

const TABLE_STATUS_STYLES: Record<string, string> = {
    available: "border-success/30 text-success",
    occupied: "border-warning/30 text-warning",
    reserved: "border-info/30 text-info",
    cleaning: "border-danger/30 text-danger",
};

/**
 * Floor/tables management panel — open/close (available/occupied), mark
 * cleaning needed / cleaned, add new tables to the floor. Split out of
 * ReservationsWorkspace; named for what it does (there is no filter UI
 * in this component) rather than the "ReservationFilters" name suggested
 * in the remediation plan.
 */
export default function TablesPanel({
    visible,
    floorTables,
    newTableNumber,
    onNewTableNumberChange,
    newTableCapacity,
    onNewTableCapacityChange,
    submitting,
    onAddTable,
    onTableStatus,
}: TablesPanelProps) {
    return (
        <AnimatePresence>
            {visible && (
                <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                    className="bg-surface border border-border rounded-xl overflow-hidden">
                    <div className="px-4 py-3 border-b border-surface-hover flex items-center justify-between">
                        <span className="text-xs font-semibold text-text">Tables</span>
                        <div className="flex gap-2 items-center">
                            <FormField
                                label="Table number"
                                srOnlyLabel
                                placeholder="Table #"
                                value={newTableNumber}
                                onChange={(e) => onNewTableNumberChange(e.target.value)}
                                type="number"
                                className="w-20 bg-surface-hover border border-border rounded-lg px-2 py-1 text-xs text-text placeholder-text-dim focus:outline-none"
                            />
                            <FormField
                                label="Seats"
                                srOnlyLabel
                                placeholder="Seats"
                                value={newTableCapacity}
                                onChange={(e) => onNewTableCapacityChange(e.target.value)}
                                type="number"
                                className="w-16 bg-surface-hover border border-border rounded-lg px-2 py-1 text-xs text-text placeholder-text-dim focus:outline-none"
                            />
                            <button onClick={onAddTable} disabled={!newTableNumber || submitting}
                                className="bg-accent text-black rounded-lg px-3 py-1 text-xs font-semibold disabled:opacity-50">
                                Add
                            </button>
                        </div>
                    </div>
                    {floorTables.length === 0 ? (
                        <p className="text-xs text-text-dim text-center py-6">No tables set up yet</p>
                    ) : (
                        <div className="p-3 grid grid-cols-2 sm:grid-cols-4 gap-2">
                            {floorTables.map((t) => (
                                <div key={t.id} className={`border rounded-lg p-2.5 ${TABLE_STATUS_STYLES[t.status] || "border-border"}`}>
                                    <p className="text-xs font-semibold text-text">Table {t.table_number}</p>
                                    <p className="text-[10px] text-text-dim">{t.capacity} seats · {t.status}</p>
                                    <div className="flex gap-1 mt-1.5">
                                        {t.status !== "occupied" && (
                                            <button onClick={() => onTableStatus(t.id, "occupied")} title="Open / seat"
                                                className="text-[9px] px-1.5 py-0.5 rounded bg-surface-hover text-text-muted hover:text-warning">Open</button>
                                        )}
                                        {t.status !== "available" && (
                                            <button onClick={() => onTableStatus(t.id, "available")} title="Close / free up"
                                                className="text-[9px] px-1.5 py-0.5 rounded bg-surface-hover text-text-muted hover:text-success">Close</button>
                                        )}
                                        {t.status !== "cleaning" && (
                                            <button onClick={() => onTableStatus(t.id, "cleaning")} title="Mark cleaning needed"
                                                className="text-[9px] px-1.5 py-0.5 rounded bg-surface-hover text-text-muted hover:text-danger" aria-label="Mark cleaning needed">
                                                <Brush className="w-2.5 h-2.5 inline" />
                                            </button>
                                        )}
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </motion.div>
            )}
        </AnimatePresence>
    );
}
