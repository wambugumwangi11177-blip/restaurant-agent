"use client";

import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import FormField from "@/components/ui/FormField";

interface Table {
    id: number;
    table_id?: number;
    table_number: number;
    capacity: number;
}

interface ReservationFormProps {
    visible: boolean;
    onClose: () => void;
    customerName: string;
    onCustomerNameChange: (v: string) => void;
    customerPhone: string;
    onCustomerPhoneChange: (v: string) => void;
    partySize: string;
    onPartySizeChange: (v: string) => void;
    reservationDate: string;
    onReservationDateChange: (v: string) => void;
    reservationTime: string;
    onReservationTimeChange: (v: string) => void;
    notes: string;
    onNotesChange: (v: string) => void;
    tableId: string;
    onTableIdChange: (v: string) => void;
    suggestedTables: Table[] | null;
    floorTables: Table[];
    submitting: boolean;
    onSubmit: () => void;
}

/** New Booking creation form — extracted from ReservationsWorkspace. */
export default function ReservationForm({
    visible,
    onClose,
    customerName,
    onCustomerNameChange,
    customerPhone,
    onCustomerPhoneChange,
    partySize,
    onPartySizeChange,
    reservationDate,
    onReservationDateChange,
    reservationTime,
    onReservationTimeChange,
    notes,
    onNotesChange,
    tableId,
    onTableIdChange,
    suggestedTables,
    floorTables,
    submitting,
    onSubmit,
}: ReservationFormProps) {
    return (
        <AnimatePresence>
            {visible && (
                <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                    className="bg-surface border border-accent/20 rounded-xl overflow-hidden">
                    <div className="px-4 py-3 border-b border-surface-hover flex items-center justify-between">
                        <span className="text-xs font-semibold text-text">New Booking</span>
                        <button onClick={onClose} aria-label="Close form"><X className="w-4 h-4 text-text-dim" /></button>
                    </div>
                    <div className="p-4 grid grid-cols-2 sm:grid-cols-3 gap-3">
                        <FormField
                            label="Customer name"
                            srOnlyLabel
                            placeholder="Customer name"
                            value={customerName}
                            onChange={(e) => onCustomerNameChange(e.target.value)}
                            className="col-span-2 sm:col-span-1 bg-surface-hover border border-border rounded-lg px-3 py-2 text-xs text-text placeholder-text-dim focus:border-accent/50 focus:outline-none"
                        />
                        <FormField
                            label="Phone"
                            srOnlyLabel
                            placeholder="Phone"
                            value={customerPhone}
                            onChange={(e) => onCustomerPhoneChange(e.target.value)}
                            className="bg-surface-hover border border-border rounded-lg px-3 py-2 text-xs text-text placeholder-text-dim focus:border-accent/50 focus:outline-none"
                        />
                        <FormField
                            label="Party size"
                            srOnlyLabel
                            placeholder="Party size"
                            value={partySize}
                            onChange={(e) => onPartySizeChange(e.target.value)}
                            type="number"
                            className="bg-surface-hover border border-border rounded-lg px-3 py-2 text-xs text-text placeholder-text-dim focus:border-accent/50 focus:outline-none"
                        />
                        <FormField
                            label="Reservation date"
                            srOnlyLabel
                            value={reservationDate}
                            onChange={(e) => onReservationDateChange(e.target.value)}
                            type="date"
                            className="bg-surface-hover border border-border rounded-lg px-3 py-2 text-xs text-text focus:border-accent/50 focus:outline-none"
                        />
                        <FormField
                            label="Reservation time"
                            srOnlyLabel
                            value={reservationTime}
                            onChange={(e) => onReservationTimeChange(e.target.value)}
                            type="time"
                            className="bg-surface-hover border border-border rounded-lg px-3 py-2 text-xs text-text focus:border-accent/50 focus:outline-none"
                        />
                        <FormField
                            label="Notes"
                            srOnlyLabel
                            placeholder="Notes"
                            value={notes}
                            onChange={(e) => onNotesChange(e.target.value)}
                            className="col-span-2 bg-surface-hover border border-border rounded-lg px-3 py-2 text-xs text-text placeholder-text-dim focus:border-accent/50 focus:outline-none"
                        />
                        <div className="flex flex-col gap-1">
                            <label htmlFor="new-booking-table" className="sr-only">Table</label>
                            <select id="new-booking-table" value={tableId} onChange={(e) => onTableIdChange(e.target.value)}
                                className="bg-surface-hover border border-border rounded-lg px-3 py-2 text-xs text-text focus:border-accent/50 focus:outline-none">
                                <option value="">No table assigned</option>
                                {suggestedTables !== null ? (
                                    <>
                                        <optgroup label="Suggested (best fit, available)">
                                            {suggestedTables.map((t) => <option key={t.table_id} value={t.table_id}>Table {t.table_number} (seats {t.capacity})</option>)}
                                        </optgroup>
                                        {floorTables.filter((t) => !suggestedTables.some((s) => s.table_id === t.id)).length > 0 && (
                                            <optgroup label="Other tables">
                                                {floorTables.filter((t) => !suggestedTables.some((s) => s.table_id === t.id))
                                                    .map((t) => <option key={t.id} value={t.id}>Table {t.table_number} (seats {t.capacity})</option>)}
                                            </optgroup>
                                        )}
                                    </>
                                ) : (
                                    floorTables.map((t) => <option key={t.id} value={t.id}>Table {t.table_number} (seats {t.capacity})</option>)
                                )}
                            </select>
                        </div>
                        <button onClick={onSubmit} disabled={!customerName || !reservationDate || !reservationTime || submitting}
                            className="bg-accent text-black rounded-lg px-4 py-2 text-xs font-semibold disabled:opacity-50">
                            {submitting ? "Booking..." : "Book"}
                        </button>
                    </div>
                </motion.div>
            )}
        </AnimatePresence>
    );
}
