"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import api from "@/lib/api";
import { takePhoto } from "@/lib/capturePhoto";
import { hasModule, loadSetup, type SetupPayload } from "@/lib/storeSetup";

type Supplier = { id: number; name: string; brings: string };
type Delivery = {
  id: number;
  supplier: string | null;
  lines: { item_name: string; quantity: number; unit: string }[];
  photos: { kind: string }[];
  ai_label?: string;
};

export default function DeliveriesPage() {
  const [setup, setSetup] = useState<SetupPayload | null>(null);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [rows, setRows] = useState<Delivery[]>([]);
  const [supplierId, setSupplierId] = useState("");
  const [itemName, setItemName] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [unit, setUnit] = useState("kg");
  const [invoice, setInvoice] = useState<File | null>(null);
  const [goods, setGoods] = useState<File | null>(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function refresh() {
    const next = await loadSetup();
    setSetup(next);
    if (!hasModule(next, "deliveries")) return;
    const [supplierResponse, deliveryResponse] = await Promise.all([
      api.get("/api/v1/store/suppliers").catch(() => ({ data: [] })),
      api.get("/api/v1/store/deliveries"),
    ]);
    setSuppliers(supplierResponse.data);
    setRows(deliveryResponse.data);
    if (!supplierId && supplierResponse.data[0]) setSupplierId(String(supplierResponse.data[0].id));
  }

  useEffect(() => {
    refresh().catch(() => setError("Deliveries could not be loaded."));
  }, []);

  async function useCamera(which: "invoice" | "goods", input: HTMLInputElement) {
    const photo = await takePhoto().catch(() => null);
    if (photo) {
      if (which === "invoice") setInvoice(photo);
      else setGoods(photo);
      return;
    }
    input.click();
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!invoice || !goods || !supplierId) {
      setError("Choose the supplier, the invoice photo, and a photo of the goods.");
      return;
    }
    setSaving(true);
    setError("");
    const body = new FormData();
    body.append("supplier_id", supplierId);
    body.append("lines", JSON.stringify([{ item_name: itemName, quantity: Number(quantity), unit }]));
    body.append("invoice", invoice);
    body.append("goods", goods);
    try {
      await api.post("/api/v1/store/deliveries", body, { headers: { "Content-Type": "multipart/form-data" } });
      setItemName("");
      setInvoice(null);
      setGoods(null);
      await refresh();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "That delivery was not saved.");
    } finally {
      setSaving(false);
    }
  }

  if (setup && !hasModule(setup, "deliveries")) {
    return (
      <section className="owner-glass-panel rounded-3xl p-4">
        <h2 className="font-semibold">Deliveries are locked</h2>
        <p className="mt-2 text-sm leading-6 text-zinc-300">Answer the delivery question first. Then you can key quantities and take the two photos.</p>
        <Link href="/store/questions" className="mt-4 inline-flex min-h-11 items-center rounded-full bg-white px-4 font-semibold text-black">Open questions</Link>
      </section>
    );
  }

  return (
    <div className="space-y-4">
      <form onSubmit={save} className="owner-glass-panel space-y-3 rounded-3xl p-4">
        <p className="text-sm leading-6 text-zinc-300">Key the quantities. Prices stay with the owner. Both photos are required.</p>
        <label className="block text-sm">Supplier
          <select required value={supplierId} onChange={(event) => setSupplierId(event.target.value)} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/40 px-3">
            <option value="">Choose</option>
            {suppliers.map((supplier) => <option key={supplier.id} value={supplier.id}>{supplier.name} · {supplier.brings}</option>)}
          </select>
        </label>
        {suppliers.length === 0 && <Link href="/store/suppliers" className="block text-sm text-zinc-300">Add a supplier first</Link>}
        <label className="block text-sm">Item
          <input required value={itemName} onChange={(event) => setItemName(event.target.value)} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3" />
        </label>
        <div className="grid grid-cols-2 gap-3">
          <label className="block text-sm">Quantity
            <input required inputMode="decimal" value={quantity} onChange={(event) => setQuantity(event.target.value)} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3" />
          </label>
          <label className="block text-sm">Unit
            <input required value={unit} onChange={(event) => setUnit(event.target.value)} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3" />
          </label>
        </div>
        <PhotoField label="Invoice photo" file={invoice} onFile={setInvoice} onCamera={useCamera.bind(null, "invoice")} />
        <PhotoField label="Goods photo" file={goods} onFile={setGoods} onCamera={useCamera.bind(null, "goods")} />
        {error && <p className="text-sm text-red-300">{error}</p>}
        <button type="submit" disabled={saving} className="min-h-11 w-full rounded-full bg-white font-semibold text-black disabled:opacity-50">
          {saving ? "Saving…" : "Receive delivery"}
        </button>
      </form>
      <Link href="/store/questions" className="block text-center text-sm text-zinc-400">Next question</Link>
      <ul className="space-y-2">
        {rows.map((row) => (
          <li key={row.id} className="owner-glass-panel rounded-3xl px-4 py-3 text-sm">
            <p className="font-semibold">{row.supplier}</p>
            {row.lines.map((line) => (
              <p key={line.item_name} className="text-zinc-300">{line.quantity} {line.unit} {line.item_name}</p>
            ))}
            <p className="mt-1 text-xs text-zinc-500">{row.photos.length} photos · {row.ai_label || "AI"}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}

function PhotoField({
  label,
  file,
  onFile,
  onCamera,
}: {
  label: string;
  file: File | null;
  onFile: (file: File | null) => void;
  onCamera: (input: HTMLInputElement) => void;
}) {
  return (
    <div className="text-sm">
      <p>{label}</p>
      <div className="mt-1 flex gap-2">
        <label className="inline-flex min-h-11 flex-1 items-center justify-center rounded-full border border-white/20 px-3">
          {file ? file.name : "Choose or take photo"}
          <input
            type="file"
            accept="image/*"
            capture="environment"
            className="sr-only"
            onChange={(event) => onFile(event.target.files?.[0] ?? null)}
          />
        </label>
        <button
          type="button"
          className="min-h-11 rounded-full border border-white/20 px-3"
          onClick={(event) => {
            const input = event.currentTarget.parentElement?.querySelector("input");
            if (input) onCamera(input);
          }}
        >
          Camera
        </button>
      </div>
    </div>
  );
}
