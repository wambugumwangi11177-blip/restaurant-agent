"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";

type Line = { id: number; item_name: string; quantity: number; unit: string };
type Photo = { id: number; kind: string };
type Delivery = {
  id: number;
  supplier: string | null;
  lines: Line[];
  photos: Photo[];
  ai_label?: string;
  ai_note?: string;
  mismatches?: { item_name: string; source: string; keyed: number; seen: number | null }[];
};

export default function DeliveryPriceConfirm() {
  const [rows, setRows] = useState<Delivery[]>([]);
  const [prices, setPrices] = useState<Record<number, string>>({});
  const [photos, setPhotos] = useState<Record<string, string>>({});
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function load() {
    const response = await api.get("/api/v1/store/deliveries");
    setRows(response.data);
  }

  useEffect(() => {
    load().catch(() => setError("Deliveries could not be loaded."));
  }, []);

  async function showPhoto(deliveryId: number, photo: Photo) {
    const key = `${deliveryId}-${photo.id}`;
    if (photos[key]) return;
    const response = await api.get(`/api/v1/store/deliveries/${deliveryId}/photos/${photo.id}`, { responseType: "blob" });
    setPhotos((current) => ({ ...current, [key]: URL.createObjectURL(response.data) }));
  }

  async function confirm(delivery: Delivery) {
    setError("");
    setMessage("");
    const lines = delivery.lines
      .filter((line) => prices[line.id])
      .map((line) => ({ line_id: line.id, cost_per_unit_kes: Number(prices[line.id]) }));
    if (!lines.length) return;
    try {
      await api.post(`/api/v1/store/deliveries/${delivery.id}/prices`, { lines });
      setMessage("Prices saved from the invoice. The storekeeper does not see them.");
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "The prices were not saved.");
    }
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-zinc-400">Key unit prices from the invoice photo. Jack never sees these numbers.</p>
      {error && <p className="text-sm text-red-300">{error}</p>}
      {message && <p className="text-sm text-[var(--text)]">{message}</p>}
      {rows.length === 0 ? (
        <p className="owner-glass-panel rounded-3xl p-4 text-sm text-zinc-300">No deliveries yet.</p>
      ) : (
        <ul className="space-y-3">
          {rows.map((delivery) => (
            <li key={delivery.id} className="owner-glass-panel space-y-3 rounded-3xl p-4 text-sm">
              <p className="font-semibold">{delivery.supplier}</p>
              <p className="text-xs uppercase tracking-wide text-zinc-400">
                {delivery.ai_label || "AI"}
                {delivery.ai_note ? ` · ${delivery.ai_note}` : ""}
              </p>
              {(delivery.mismatches ?? []).map((mismatch) => (
                <p key={`${mismatch.item_name}-${mismatch.source}`} className="text-zinc-200">
                  AI: {mismatch.item_name} on the {mismatch.source} looks like {mismatch.seen ?? "unreadable"}, keyed{" "}
                  {mismatch.keyed}.
                </p>
              ))}
              {delivery.lines.map((line) => (
                <label key={line.id} className="block">
                  {line.quantity} {line.unit} {line.item_name}
                  <input
                    inputMode="decimal"
                    placeholder="Price per unit, KES"
                    value={prices[line.id] ?? ""}
                    onChange={(event) => setPrices((current) => ({ ...current, [line.id]: event.target.value }))}
                    className="leviii-input mt-1 min-h-11 w-full rounded-2xl px-3"
                  />
                </label>
              ))}
              <div className="flex flex-wrap gap-2">
                {delivery.photos.map((photo) => (
                  <button
                    key={photo.id}
                    type="button"
                    className="leviii-btn-ghost min-h-11 px-3"
                    onClick={() => showPhoto(delivery.id, photo)}
                  >
                    {photo.kind === "invoice" ? "View invoice photo" : "Goods"}
                  </button>
                ))}
              </div>
              {delivery.photos.map((photo) => {
                const url = photos[`${delivery.id}-${photo.id}`];
                return url ? <img key={url} src={url} alt={photo.kind} className="max-h-48 w-full rounded-2xl object-cover" /> : null;
              })}
              <button type="button" onClick={() => confirm(delivery)} className="leviii-btn-primary min-h-11 w-full">
                Confirm prices
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}