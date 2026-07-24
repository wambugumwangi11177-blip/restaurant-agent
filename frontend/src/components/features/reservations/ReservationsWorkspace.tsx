"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { Plus, LayoutGrid } from "lucide-react";
import { useToast } from "@/components/ui/Toast";
import ReservationForm from "./ReservationForm";
import TablesPanel from "./TablesPanel";
import ReservationList, { type EditForm } from "./ReservationList";
import { getErrorMessage } from "@/lib/errors";
import type { Reservation, FloorTable, ReservationAiData } from "./types";

/**
 * Bookings workspace — extends the original dashboard/reservations/page.tsx
 * (which was read-only despite the backend supporting create/status-update)
 * with an actual create form and status actions. Every tier with
 * `reservations` = RW (directive 015: Owner, Manager, Supervisor, Waiter)
 * reuses this unmodified; the write actions simply 403 server-side for a
 * tier without access, but no tier without `reservations` access at all
 * renders this component in the first place.
 *
 * Split into ReservationForm (New Booking), TablesPanel (floor/table
 * management), and ReservationList (stats + AI insights + bookings list
 * with inline edit); this file stays the state-holding composer.
 */
export default function ReservationsWorkspace() {
    const [reservations, setReservations] = useState<Reservation[]>([]);
    const [aiData, setAiData] = useState<ReservationAiData | null>(null);
    const [loading, setLoading] = useState(true);
    const [submitting, setSubmitting] = useState(false);
    const { showToast, toastNode } = useToast();
    const [showForm, setShowForm] = useState(false);

    const [customerName, setCustomerName] = useState("");
    const [customerPhone, setCustomerPhone] = useState("");
    const [partySize, setPartySize] = useState("2");
    const [reservationDate, setReservationDate] = useState("");
    const [reservationTime, setReservationTime] = useState("");
    const [notes, setNotes] = useState("");
    const [tableId, setTableId] = useState("");
    const [suggestedTables, setSuggestedTables] = useState<FloorTable[] | null>(null);

    // Floor/tables — directive 015 treats table management as part of the
    // reservations domain (no separate matrix row), so it lives here rather
    // than as its own dashboard section.
    const [floorTables, setFloorTables] = useState<FloorTable[]>([]);
    const [showTablesPanel, setShowTablesPanel] = useState(false);
    const [newTableNumber, setNewTableNumber] = useState("");
    const [newTableCapacity, setNewTableCapacity] = useState("4");

    // Edit an existing booking — date/time/party size/notes/table.
    const [editingId, setEditingId] = useState<number | null>(null);
    const [editForm, setEditForm] = useState<EditForm>({
        party_size: "", reservation_date: "", reservation_time: "", notes: "", table_id: "",
    });
    const [editSuggestedTables, setEditSuggestedTables] = useState<FloorTable[] | null>(null);

    const fetchData = async () => {
        const [resRes, aiRes, tablesRes] = await Promise.all([
            api.get("/reservations/").catch(() => ({ data: [] })),
            api.get("/ai/reservation-insights").catch(() => ({ data: null })),
            api.get("/tables/").catch(() => ({ data: [] })),
        ]);
        setReservations(Array.isArray(resRes.data) ? resRes.data : []);
        setAiData(aiRes.data);
        setFloorTables(Array.isArray(tablesRes.data) ? tablesRes.data : []);
        setLoading(false);
    };

    useEffect(() => { fetchData(); }, []);

    // Best-fit table suggestions — re-queried whenever the fields that
    // affect availability change, for the New Booking form.
    useEffect(() => {
        if (!showForm || !reservationDate || !reservationTime || !partySize) { setSuggestedTables(null); return; }
        api.get("/reservations/available-tables", {
            params: { party_size: parseInt(partySize) || 1, reservation_date: reservationDate, reservation_time: reservationTime },
        }).then((res) => setSuggestedTables(res.data)).catch(() => setSuggestedTables(null));
    }, [showForm, reservationDate, reservationTime, partySize]);

    // Same, for the inline Edit form.
    useEffect(() => {
        if (!editingId || !editForm.reservation_date || !editForm.reservation_time || !editForm.party_size) {
            setEditSuggestedTables(null);
            return;
        }
        api.get("/reservations/available-tables", {
            params: {
                party_size: parseInt(editForm.party_size) || 1,
                reservation_date: editForm.reservation_date,
                reservation_time: editForm.reservation_time,
                exclude_reservation_id: editingId,
            },
        }).then((res) => setEditSuggestedTables(res.data)).catch(() => setEditSuggestedTables(null));
    }, [editingId, editForm.reservation_date, editForm.reservation_time, editForm.party_size]);

    const resetForm = () => {
        setCustomerName(""); setCustomerPhone(""); setPartySize("2");
        setReservationDate(""); setReservationTime(""); setNotes(""); setTableId("");
    };

    const handleCreate = async () => {
        if (!customerName || !reservationDate || !reservationTime) return;
        setSubmitting(true);
        try {
            await api.post("/reservations/", {
                customer_name: customerName,
                customer_phone: customerPhone,
                party_size: parseInt(partySize) || 2,
                reservation_date: reservationDate,
                reservation_time: reservationTime,
                notes,
                table_id: tableId ? parseInt(tableId) : null,
            });
            showToast(`Booked for ${customerName}`);
            setShowForm(false);
            resetForm();
            await fetchData();
        } catch (err) {
            showToast(getErrorMessage(err, "Failed to create booking"), "error");
        }
        setSubmitting(false);
    };

    const handleStatusChange = async (id: number, status: string) => {
        setSubmitting(true);
        try {
            await api.post(`/reservations/${id}/status`, { status });
            await fetchData();
        } catch (err) {
            showToast(getErrorMessage(err, "Failed to update booking"), "error");
        }
        setSubmitting(false);
    };

    const openEdit = (res: Reservation) => {
        if (editingId === res.id) { setEditingId(null); return; }
        setEditingId(res.id);
        setEditForm({
            party_size: String(res.party_size ?? ""),
            reservation_date: res.reservation_date || "",
            reservation_time: (res.reservation_time || "").slice(0, 5),
            notes: res.notes || "",
            table_id: res.table_id != null ? String(res.table_id) : "",
        });
    };

    const handleSaveEdit = async (id: number) => {
        setSubmitting(true);
        try {
            await api.put(`/reservations/${id}`, {
                party_size: editForm.party_size ? parseInt(editForm.party_size) : undefined,
                reservation_date: editForm.reservation_date || undefined,
                reservation_time: editForm.reservation_time || undefined,
                notes: editForm.notes,
                table_id: editForm.table_id ? parseInt(editForm.table_id) : null,
            });
            showToast("Booking updated");
            setEditingId(null);
            await fetchData();
        } catch (err) {
            showToast(getErrorMessage(err, "Failed to update booking"), "error");
        }
        setSubmitting(false);
    };

    const handleAddTable = async () => {
        if (!newTableNumber) return;
        setSubmitting(true);
        try {
            await api.post("/tables/", {
                table_number: parseInt(newTableNumber),
                capacity: parseInt(newTableCapacity) || 4,
            });
            showToast(`Added Table ${newTableNumber}`);
            setNewTableNumber(""); setNewTableCapacity("4");
            await fetchData();
        } catch (err) {
            showToast(getErrorMessage(err, "Failed to add table"), "error");
        }
        setSubmitting(false);
    };

    const handleTableStatus = async (tableId: number, status: string) => {
        setSubmitting(true);
        try {
            await api.post(`/tables/${tableId}/status`, { status });
            await fetchData();
        } catch (err) {
            showToast(getErrorMessage(err, "Failed to update table"), "error");
        }
        setSubmitting(false);
    };

    if (loading) {
        return (
            <div className="space-y-3">
                {[...Array(4)].map((_, i) => (
                    <div key={i} className="bg-surface rounded-xl h-16 animate-pulse" />
                ))}
            </div>
        );
    }

    const today = new Date().toISOString().split("T")[0];
    const todayBookings = reservations.filter((r) => r.reservation_date === today);
    const upcoming = reservations.filter((r) => r.reservation_date >= today && r.status === "confirmed");

    return (
        <div className="space-y-5">
            {toastNode}

            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-xl font-bold text-text">Bookings</h1>
                    <p className="text-sm text-text-dim mt-0.5">
                        {todayBookings.length} today · {upcoming.length} coming up
                    </p>
                </div>
                <div className="flex gap-2">
                    <button onClick={() => setShowTablesPanel(!showTablesPanel)}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-surface-hover border border-border rounded-lg text-xs text-text-muted hover:text-text transition-all">
                        <LayoutGrid className="w-3 h-3" />
                        Tables
                    </button>
                    <button onClick={() => setShowForm(!showForm)}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-accent/10 border border-accent/30 rounded-lg text-xs text-accent hover:bg-accent/20 transition-all">
                        <Plus className="w-3 h-3" />
                        New Booking
                    </button>
                </div>
            </div>

            <TablesPanel
                visible={showTablesPanel}
                floorTables={floorTables}
                newTableNumber={newTableNumber}
                onNewTableNumberChange={setNewTableNumber}
                newTableCapacity={newTableCapacity}
                onNewTableCapacityChange={setNewTableCapacity}
                submitting={submitting}
                onAddTable={handleAddTable}
                onTableStatus={handleTableStatus}
            />

            <ReservationForm
                visible={showForm}
                onClose={() => setShowForm(false)}
                customerName={customerName}
                onCustomerNameChange={setCustomerName}
                customerPhone={customerPhone}
                onCustomerPhoneChange={setCustomerPhone}
                partySize={partySize}
                onPartySizeChange={setPartySize}
                reservationDate={reservationDate}
                onReservationDateChange={setReservationDate}
                reservationTime={reservationTime}
                onReservationTimeChange={setReservationTime}
                notes={notes}
                onNotesChange={setNotes}
                tableId={tableId}
                onTableIdChange={setTableId}
                suggestedTables={suggestedTables}
                floorTables={floorTables}
                submitting={submitting}
                onSubmit={handleCreate}
            />

            <ReservationList
                reservations={reservations}
                floorTables={floorTables}
                aiData={aiData}
                submitting={submitting}
                editingId={editingId}
                editForm={editForm}
                onEditFormChange={setEditForm}
                editSuggestedTables={editSuggestedTables}
                onOpenEdit={openEdit}
                onCancelEdit={() => setEditingId(null)}
                onSaveEdit={handleSaveEdit}
                onStatusChange={handleStatusChange}
            />
        </div>
    );
}
