"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import PhotoField from "@/components/store/PhotoField";
import api from "@/lib/api";

type ZoneStatus = {
  id: number;
  name: string;
  open_done: boolean;
  close_done: boolean;
};

type StatusPayload = {
  business_date: string;
  zones: ZoneStatus[];
  open_complete: boolean;
  close_complete: boolean;
};

export default function DayPhotosPage() {
  const [phase, setPhase] = useState<"open" | "close">("open");
  const [status, setStatus] = useState<StatusPayload | null>(null);
  const [zoneId, setZoneId] = useState<number | null>(null);
  const [photo, setPhoto] = useState<File | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    const response = await api.get("/api/v1/store/day-photos/status");
    setStatus(response.data);
    if (!zoneId && response.data.zones?.[0]) setZoneId(response.data.zones[0].id);
  }, [zoneId]);

  useEffect(() => {
    refresh().catch(() => setError("Day photos could not be loaded."));
  }, [refresh]);

  async function send() {
    if (!photo || zoneId == null) {
      setError("Choose a zone and take a photo.");
      return;
    }
    setError("");
    setMessage("");
    const body = new FormData();
    body.set("zone_id", String(zoneId));
    body.set("phase", phase);
    body.set("photo", photo);
    try {
      await api.post("/api/v1/store/day-photos", body, { headers: { "Content-Type": "multipart/form-data" } });
      setMessage("Saved. The owner can see it in the feed.");
      setPhoto(null);
      await refresh();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "That photo was not saved.");
    }
  }

  const zone = status?.zones.find((row) => row.id === zoneId);

  return (
    <div className="space-y-4">
      <section className="owner-glass-panel rounded-3xl p-4">
        <h2 className="font-semibold">Zone photos</h2>
        <p className="mt-2 text-sm leading-6 text-zinc-300">
          Take one photo in each storage zone at day open and again at day close. You need both before stock moves or the day close.
        </p>
        {status && <p className="mt-2 text-xs text-zinc-500">Today: {status.business_date}</p>}
      </section>
      <div className="flex gap-2">
        {(["open", "close"] as const).map((value) => (
          <button
            key={value}
            type="button"
            className={`owner-chip ${phase === value ? "is-on" : ""}`}
            onClick={() => setPhase(value)}
          >
            {value === "open" ? "Day open" : "Day close"}
          </button>
        ))}
      </div>
      {status?.zones.map((row) => (
        <p key={row.id} className="owner-quiet">
          {row.name}: {row.open_done ? "open done" : "open waiting"}, {row.close_done ? "close done" : "close waiting"}
        </p>
      ))}
      <section className="owner-glass-panel space-y-3 rounded-3xl p-4">
        <label className="block text-sm">
          Zone
          <select
            value={zoneId ?? ""}
            onChange={(event) => setZoneId(Number(event.target.value))}
            className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/40 px-3"
          >
            {(status?.zones ?? []).map((row) => (
              <option key={row.id} value={row.id}>
                {row.name}
              </option>
            ))}
          </select>
        </label>
        {zone && (phase === "open" ? zone.open_done : zone.close_done) ? (
          <p className="text-sm text-zinc-300">This zone already has a {phase} photo today.</p>
        ) : (
          <>
            <PhotoField label="Zone photo" file={photo} onFile={setPhoto} />
            <button type="button" onClick={send} className="min-h-11 w-full rounded-full bg-white font-semibold text-black">
              Save {phase} photo
            </button>
          </>
        )}
        {error && <p className="text-sm text-red-300">{error}</p>}
        {message && <p className="text-sm text-zinc-200">{message}</p>}
      </section>
      <Link href="/store" className="text-sm underline">
        Back to home
      </Link>
    </div>
  );
}