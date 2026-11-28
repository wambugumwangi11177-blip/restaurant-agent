"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import { takePhoto } from "@/lib/capturePhoto";
import { hasModule, loadSetup, type SetupPayload } from "@/lib/storeSetup";

type Supplier = { id: number; name: string; brings: string };
type StockItem = { id: number; item_name: string; unit: string; quantity: number };
type Delivery = {
  id: number;
  supplier: string | null;
  lines: { item_name: string; quantity: number; unit: string }[];
  photos: { kind: string }[];
  check_label?: string;
};

type LineDraft =
  | { mode: "existing"; item_id: string; quantity: string }
  | { mode: "new"; item_name: string; unit: string; quantity: string };

const EMPTY_LINE: LineDraft = { mode: "existing", item_id: "", quantity: "1" };

export default function DeliveriesPage() {
  const [setup, setSetup] = useState<SetupPayload | null>(null);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [stockItems, setStockItems] = useState<StockItem[]>([]);
  const [units, setUnits] = useState<string[]>(["kg", "g", "L", "ml", "pcs", "packet", "tray", "crate", "bag"]);
  const [rows, setRows] = useState<Delivery[]>([]);
  const [supplierId, setSupplierId] = useState("");
  const [lines, setLines] = useState<LineDraft[]>([{ ...EMPTY_LINE }]);
  const [invoice, setInvoice] = useState<File | null>(null);
  const [goods, setGoods] = useState<File | null>(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const refresh = useCallback(async () => {
    const next = await loadSetup();
    setSetup(next);
    if (!hasModule(next, "deliveries")) return;
    const [supplierResponse, deliveryResponse, itemResponse, unitResponse] = await Promise.all([
      api.get("/api/v1/store/suppliers").catch(() => ({ data: [] })),
      api.get("/api/v1/store/deliveries"),
      api.get("/api/v1/store/items"),
      api.get("/api/v1/store/inventory-units"),
    ]);
    setSuppliers(supplierResponse.data);
    setRows(deliveryResponse.data);
    setStockItems((itemResponse.data.items ?? []).map((i: StockItem) => i));
    if (unitResponse.data?.units) setUnits(unitResponse.data.units);
    if (!supplierId && supplierResponse.data[0]) setSupplierId(String(supplierResponse.data[0].id));
  }, [supplierId]);

  useEffect(() => {
    refresh().catch(() => setError("Deliveries could not be loaded."));
  }, [refresh]);

  function updateLine(index: number, patch: Partial<LineDraft>) {
    setLines((current) => current.map((row, i) => (i === index ? { ...row, ...patch } as LineDraft : row)));
  }

  function addLine() {
    setLines((current) => [...current, { ...EMPTY_LINE }]);
  }

  function removeLine(index: number) {
    setLines((current) => (current.length <= 1 ? current : current.filter((_, i) => i !== index)));
  }

  function linePayload(row: LineDraft) {
    const qty = Number(row.quantity);
    if (!Number.isFinite(qty) || qty <= 0) throw new Error("Each line needs a quantity.");
    if (row.mode === "existing") {
      if (!row.item_id) throw new Error("Pick a stock item on every line.");
      return { item_id: Number(row.item_id), quantity: qty };
    }
    if (!row.item_name.trim()) throw new Error("Name the new stock item.");
    return { item_name: row.item_name.trim(), unit: row.unit, quantity: qty };
  }

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
    try {
      const parsed = lines.map(linePayload);
      const body = new FormData();
      body.append("supplier_id", supplierId);
      body.append("lines", JSON.stringify(parsed));
      body.append("invoice", invoice);
      body.append("goods", goods);
      await api.post("/api/v1/store/deliveries", body, { headers: { "Content-Type": "multipart/form-data" } });
      setLines([{ ...EMPTY_LINE }]);
      setInvoice(null);
      setGoods(null);
      await refresh();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } }; message?: string })?.response?.data?.detail;
      const msg = (err as Error)?.message;
      setError(typeof detail === "string" ? detail : typeof msg === "string" ? msg : "That delivery was not saved.");
    } finally {
      setSaving(false);
    }
  }

  if (setup && !hasModule(setup, "deliveries")) {
    return (
      <section className="owner-glass-panel rounded-3xl p-4">
        <h2 className="font-semibold">Deliveries are locked</h2>
        <p className="mt-2 text-sm leading-6 text-zinc-300">Answer the delivery question first. Then you can key quantities and take the two photos.</p>
        <Link href="/store/questions" className="mt-4 inline-flex min-h-11 items-center leviii-btn-primary px-4">Open questions</Link>
      </section>
    );
  }

  return (
    <div className="space-y-4">
      <form onSubmit={save} className="owner-glass-panel space-y-3 rounded-3xl p-4">
        <p className="text-sm leading-6 text-zinc-300">One delivery: one supplier, invoice photo, goods photo, and as many stock lines as arrived.</p>
        <label className="block text-sm">Supplier
          <select required aria-label="supplier" value={supplierId} onChange={(event) => setSupplierId(event.target.value)} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/40 px-3">
            <option value="">Choose</option>
            {suppliers.map((supplier) => <option key={supplier.id} value={supplier.id}>{supplier.name} · {supplier.brings}</option>)}
          </select>
        </label>
        {suppliers.length === 0 && <Link href="/store/suppliers" className="block text-sm text-zinc-300">Add a supplier first</Link>}
        <div className="space-y-3">
          <p className="text-sm font-medium">Lines</p>
          {lines.map((row, index) => (
            <DeliveryLineRow
              key={index}
              row={row}
              index={index}
              stockItems={stockItems}
              units={units}
              onChange={updateLine}
              onRemove={() => removeLine(index)}
            />
          ))}
          <button type="button" onClick={addLine} className="min-h-11 w-full rounded-2xl border border-dashed border-white/25 text-sm">
            Add another line
          </button>
        </div>
        <PhotoField label="Invoice photo" file={invoice} onFile={setInvoice} onCamera={useCamera.bind(null, "invoice")} />
        <PhotoField label="Goods photo" file={goods} onFile={setGoods} onCamera={useCamera.bind(null, "goods")} />
        {error && <p className="text-sm text-red-300">{error}</p>}
        <button type="submit" disabled={saving} className="min-h-11 w-full leviii-btn-primary disabled:opacity-50">
          {saving ? "Saving…" : "Receive delivery"}
        </button>
      </form>
      <ul className="space-y-2">
        {rows.map((row) => (
          <li key={row.id} className="owner-glass-panel rounded-3xl px-4 py-3 text-sm">
            <p className="font-semibold">{row.supplier}</p>
            <ul className="mt-1 space-y-0.5 border-l border-white/10 pl-3">
              {row.lines.map((line) => (
                <li key={`${row.id}-${line.item_name}-${line.quantity}`} className="text-zinc-200">
                  <span className="font-medium">{line.quantity} {line.unit}</span> {line.item_name}
                </li>
              ))}
            </ul>
            <p className="mt-2 text-xs text-zinc-500">{row.photos.length} photos{row.check_label ? ` · ${row.check_label}` : ""}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}

function DeliveryLineRow({
  row,
  index,
  stockItems,
  units,
  onChange,
  onRemove,
}: {
  row: LineDraft;
  index: number;
  stockItems: StockItem[];
  units: string[];
  onChange: (index: number, patch: Partial<LineDraft>) => void;
  onRemove: () => void;
}) {
  const unitForExisting =
    row.mode === "existing" && row.item_id
      ? stockItems.find((i) => String(i.id) === row.item_id)?.unit ?? "—"
      : "—";
  return (
    <div className="rounded-2xl border border-white/10 p-3 space-y-2">
      <div className="flex gap-2 text-xs">
        <button
          type="button"
          className={row.mode === "existing" ? "font-semibold text-white" : "text-zinc-500"}
          onClick={() => onChange(index, { mode: "existing", item_id: "", quantity: row.quantity })}
        >
          From stock list
        </button>
        <button
          type="button"
          className={row.mode === "new" ? "font-semibold text-white" : "text-zinc-500"}
          onClick={() => onChange(index, { mode: "new", item_name: "", unit: "kg", quantity: row.quantity })}
        >
          New item
        </button>
        {index > 0 && (
          <button type="button" className="ml-auto text-zinc-500" onClick={onRemove}>
            Remove
          </button>
        )}
      </div>
      {row.mode === "existing" ? (
        <>
          <label className="block text-sm">Stock item
            <select
              required
              aria-label="item"
              value={row.item_id}
              onChange={(e) => onChange(index, { item_id: e.target.value })}
              className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3"
            >
              <option value="">Choose</option>
              {stockItems.map((item) => (
                <option key={item.id} value={item.id}>{item.item_name} ({item.quantity} {item.unit} on hand)</option>
              ))}
            </select>
          </label>
          <label className="block text-sm">Unit (from stock)
            <input readOnly value={unitForExisting} className="mt-1 min-h-11 w-full rounded-2xl border border-white/10 bg-black/20 px-3 text-zinc-400" />
          </label>
        </>
      ) : (
        <>
          <label className="block text-sm">New item name
            <input
              required
              aria-label="item"
              value={row.item_name}
              onChange={(e) => onChange(index, { item_name: e.target.value })}
              className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3"
            />
          </label>
          <label className="block text-sm">Unit
            <select
              value={row.unit}
              onChange={(e) => onChange(index, { unit: e.target.value })}
              className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3"
            >
              {units.map((u) => (
                <option key={u} value={u}>{u}</option>
              ))}
            </select>
          </label>
        </>
      )}
      <label className="block text-sm">Quantity
        <input
          required
          aria-label="quantity"
          inputMode="decimal"
          value={row.quantity}
          onChange={(e) => onChange(index, { quantity: e.target.value })}
          className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3"
        />
      </label>
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