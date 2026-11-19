"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import PhotoField from "@/components/store/PhotoField";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { hasModule, loadSetup, type SetupPayload } from "@/lib/storeSetup";
import { formatNairobiDateTime } from "@/lib/formatEastAfrica";

const BILLS = [
  { kind: "rent", label: "Rent" },
  { kind: "gas", label: "Gas" },
  { kind: "electricity", label: "Electricity" },
  { kind: "water", label: "Water" },
  { kind: "salaries", label: "Salaries" },
  { kind: "other", label: "Other regular bills" },
];

type Saved = {
  id: number;
  kind: string;
  label: string;
  status: string;
  message?: string;
  can_mark_paid?: boolean;
  next_due_on?: string | null;
  reminder?: string | null;
  payment_state?: string;
  created_at?: string | null;
};

function rowsForKind(rows: Saved[], kind: string) {
  return rows.filter((row) => row.kind === kind).sort((a, b) => a.id - b.id);
}

export default function CostsPage() {
  const { user } = useAuth();
  const [setup, setSetup] = useState<SetupPayload | null>(null);
  const [rows, setRows] = useState<Saved[]>([]);
  const [open, setOpen] = useState("rent");
  const [amount, setAmount] = useState("");
  const [cadence, setCadence] = useState("monthly");
  const [dueDay, setDueDay] = useState("1");
  const [otherName, setOtherName] = useState("");
  const [photo, setPhoto] = useState<File | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [payCode, setPayCode] = useState<Record<number, string>>({});
  const [payPhoto, setPayPhoto] = useState<Record<number, File | null>>({});
  const otherManager = user?.staff_role === "controller" ? "storekeeper" : "accountant";

  async function markPaid(row: Saved) {
    setError("");
    setMessage("");
    const body = new FormData();
    const code = (payCode[row.id] || "").trim();
    if (code) body.set("mpesa_code", code);
    const proof = payPhoto[row.id];
    if (proof) body.set("receipt", proof);
    try {
      const response = await api.post(`/api/v1/store/costs/${row.id}/pay`, body, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setMessage(response.data.message || "Marked paid.");
      await refresh();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "That payment was not saved.");
    }
  }

  async function refresh() {
    const next = await loadSetup();
    setSetup(next);
    if (!hasModule(next, "running-costs")) return;
    const response = await api.get("/api/v1/store/costs");
    setRows(response.data.costs ?? []);
  }

  useEffect(() => {
    refresh().catch(() => setError("Bills could not be loaded."));
  }, []);

  async function send(known: boolean, delegateTo = "") {
    setError("");
    setMessage("");
    const bill = BILLS.find((item) => item.kind === open);
    const body = new FormData();
    body.set("kind", open);
    body.set("label", open === "other" ? otherName : bill?.label || open);
    body.set("known", known ? "yes" : "no");
    body.set("cadence", cadence);
    body.set("due_day", dueDay);
    if (known) body.set("amount_kes", amount);
    if (!known) body.set("delegate_to", delegateTo);
    if (photo) body.set("receipt", photo);
    try {
      const response = await api.post("/api/v1/store/costs", body, { headers: { "Content-Type": "multipart/form-data" } });
      setMessage(response.data.message || "Sent to the owner.");
      setAmount("");
      setPhoto(null);
      await refresh();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "That bill was not saved.");
    }
  }

  if (setup && !hasModule(setup, "running-costs")) {
    return (
      <section className="owner-glass-panel rounded-3xl p-4">
        <h2 className="font-semibold">Bills are locked</h2>
        <p className="mt-2 text-sm text-zinc-300">They open when the questions say you know the regular bills.</p>
        <Link href="/store/questions" className="mt-4 inline-flex min-h-11 items-center rounded-full bg-white px-4 font-semibold text-black">Open questions</Link>
      </section>
    );
  }

  return (
    <div className="space-y-4">
      <section className="owner-glass-panel rounded-3xl p-4">
        <h2 className="font-semibold">Regular bills</h2>
        <p className="mt-2 text-sm leading-6 text-zinc-300">
          Do you know what we pay for each one? If you know it, send the amount. You will not see a total afterwards.
        </p>
      </section>
      {BILLS.map((bill) => {
        const saved = rowsForKind(rows, bill.kind);
        const pending = saved.filter((row) => row.status === "needs_approval");
        const latestPending = pending[pending.length - 1];
        const earlierPending = pending.slice(0, -1);
        const approved = saved.filter((row) => row.status === "approved");
        const activeApproved = approved[approved.length - 1];
        const unknown = saved.filter((row) => row.status === "unknown");
        const latestUnknown = unknown[unknown.length - 1];
        const active = open === bill.kind;
        return (
          <section key={bill.kind} className="owner-glass-panel rounded-3xl p-4">
            <button type="button" className="min-h-11 w-full text-left font-semibold" onClick={() => setOpen(bill.kind)}>
              {bill.label}
            </button>
            {(latestPending || activeApproved || latestUnknown) && (
              <div className="mt-2 space-y-2 border-t border-white/10 pt-2">
                {latestPending && (
                  <p className="text-sm text-zinc-400">
                    Sent to the owner on {formatNairobiDateTime(latestPending.created_at)}.
                  </p>
                )}
                {earlierPending.length > 0 && (
                  <details className="text-xs text-zinc-500">
                    <summary className="cursor-pointer">
                      {earlierPending.length} earlier submission{earlierPending.length === 1 ? "" : "s"}
                    </summary>
                    <ul className="mt-1 list-inside list-disc space-y-0.5 pl-1">
                      {earlierPending.map((row) => (
                        <li key={row.id}>{formatNairobiDateTime(row.created_at) || "Earlier"}</li>
                      ))}
                    </ul>
                  </details>
                )}
                {latestUnknown && !latestPending && (
                  <p className="text-sm text-zinc-400">Marked unknown.</p>
                )}
                {activeApproved && (
                  <>
                    {activeApproved.payment_state === "paid" ? (
                      <p className="text-sm text-zinc-400">Marked paid.</p>
                    ) : (
                      <p className="text-sm text-zinc-400">Approved by the owner.</p>
                    )}
                    {activeApproved.next_due_on && (
                      <p className={`text-xs ${activeApproved.reminder === "overdue" ? "text-red-300" : "text-zinc-500"}`}>
                        Due {activeApproved.next_due_on}
                        {activeApproved.reminder === "due_soon" ? " · due soon" : ""}
                        {activeApproved.reminder === "overdue" ? " · overdue" : ""}
                      </p>
                    )}
                    {activeApproved.can_mark_paid && (
                      <>
                        <label className="block text-sm">
                          M-Pesa code
                          <input
                            value={payCode[activeApproved.id] || ""}
                            onChange={(event) => setPayCode((prev) => ({ ...prev, [activeApproved.id]: event.target.value }))}
                            className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3"
                          />
                        </label>
                        <PhotoField
                          label="Payment receipt"
                          file={payPhoto[activeApproved.id] ?? null}
                          onFile={(file) => setPayPhoto((prev) => ({ ...prev, [activeApproved.id]: file }))}
                          optional
                        />
                        <button
                          type="button"
                          onClick={() => markPaid(activeApproved)}
                          className="min-h-11 w-full rounded-full border border-white/25 text-sm font-semibold"
                        >
                          Mark paid
                        </button>
                      </>
                    )}
                  </>
                )}
              </div>
            )}
            {active && (
              <div className="mt-3 space-y-3">
                {bill.kind === "other" && (
                  <label className="block text-sm">Name
                    <input value={otherName} onChange={(event) => setOtherName(event.target.value)} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3" />
                  </label>
                )}
                <label className="block text-sm">Amount (KES)
                  <input inputMode="decimal" value={amount} onChange={(event) => setAmount(event.target.value)} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3" />
                </label>
                <label className="block text-sm">How often
                  <select value={cadence} onChange={(event) => setCadence(event.target.value)} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/40 px-3">
                    <option value="weekly">Every week</option>
                    <option value="monthly">Every month</option>
                    <option value="yearly">Every year</option>
                  </select>
                </label>
                <label className="block text-sm">Due day
                  <input inputMode="numeric" value={dueDay} onChange={(event) => setDueDay(event.target.value.replace(/\D/g, "").slice(0, 2))} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3" />
                </label>
                <PhotoField label="Receipt" file={photo} onFile={setPhoto} optional />
                <button type="button" onClick={() => send(true)} className="min-h-11 w-full rounded-full bg-white font-semibold text-black">I know it</button>
                <div className="grid grid-cols-2 gap-2">
                  <button type="button" onClick={() => send(false, "owner")} className="min-h-11 rounded-full border border-white/20 text-sm">I don&apos;t know — owner</button>
                  <button type="button" onClick={() => send(false, otherManager)} className="min-h-11 rounded-full border border-white/20 text-sm">I don&apos;t know — {otherManager}</button>
                </div>
              </div>
            )}
          </section>
        );
      })}
      {error && <p className="text-sm text-red-300">{error}</p>}
      {message && <p className="text-sm text-zinc-200">{message}</p>}
    </div>
  );
}
