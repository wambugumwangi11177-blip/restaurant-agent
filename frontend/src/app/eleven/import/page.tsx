"use client";

import { useState } from "react";
import OwnerShell from "@/components/eleven/OwnerShell";
import { GlassCard, SectionLabel } from "@/components/eleven/EmptyPanels";
import api from "@/lib/api";

type PreviewRow = { row: number; status: string; message: string; values: Record<string, unknown> };
type Preview = { error_count: number; ready_count: number; sheets: Record<string, PreviewRow[]> };

const SHEETS = ["items", "suppliers", "recipes", "opening"];

export default function ElevenImportPage() {
  const [file, setFile] = useState<File | null>(null);
  const [sheet, setSheet] = useState("items");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [result, setResult] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const isCsv = (file?.name || "").toLowerCase().endsWith(".csv");

  async function downloadTemplate() {
    setError("");
    const response = await api.get("/api/v1/eleven/import/template", { responseType: "blob" });
    const url = URL.createObjectURL(response.data);
    const link = document.createElement("a");
    link.href = url;
    link.download = "eleven-import-template.xlsx";
    link.click();
    URL.revokeObjectURL(url);
  }

  function formData() {
    const body = new FormData();
    if (file) body.append("file", file);
    if (isCsv) body.append("sheet", sheet);
    return body;
  }

  async function runPreview(event: React.FormEvent) {
    event.preventDefault();
    if (!file) return;
    setBusy(true);
    setError("");
    setResult("");
    setPreview(null);
    try {
      const response = await api.post("/api/v1/eleven/import/preview", formData(), {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setPreview(response.data);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "The file could not be read.");
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    if (!file || !preview || preview.error_count > 0) return;
    setBusy(true);
    setError("");
    try {
      const response = await api.post("/api/v1/eleven/import/confirm", formData(), {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setResult(`${response.data.inserted} new row(s). ${response.data.skipped} already present.`);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "The import was not saved.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <OwnerShell title="Import">
      <SectionLabel>Workbook</SectionLabel>
      <GlassCard>
        <p className="text-sm leading-6 text-zinc-300">
          Items, suppliers, recipes, and an opening count go into this Eleven restaurant. The cost column stays on this screen. The storekeeper does not see this page.
        </p>
        <button type="button" onClick={downloadTemplate} className="mt-4 min-h-11 rounded-full border border-white/30 px-4 text-sm font-semibold">
          Download template
        </button>
      </GlassCard>
      <form onSubmit={runPreview} className="owner-glass-panel mt-4 space-y-3 rounded-3xl p-4">
        <label className="block text-sm">
          Excel or CSV
          <input
            type="file"
            accept=".xlsx,.csv"
            required
            onChange={(event) => {
              setFile(event.target.files?.[0] ?? null);
              setPreview(null);
              setResult("");
            }}
            className="mt-1 block w-full text-sm"
          />
        </label>
        {isCsv && (
          <label className="block text-sm">
            Which sheet is this CSV?
            <select value={sheet} onChange={(event) => setSheet(event.target.value)} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/40 px-3">
              {SHEETS.map((name) => <option key={name}>{name}</option>)}
            </select>
          </label>
        )}
        {error && <p className="text-sm text-red-300">{error}</p>}
        <button type="submit" disabled={busy || !file} className="min-h-11 w-full rounded-full bg-white font-semibold text-black disabled:opacity-50">
          {busy ? "Working…" : "Preview"}
        </button>
      </form>
      {preview && (
        <section className="mt-4 space-y-3">
          <p className="text-sm text-zinc-300">{preview.ready_count} rows ready. {preview.error_count} with errors.</p>
          {Object.entries(preview.sheets).map(([name, rows]) => (
            <div key={name} className="owner-glass-panel rounded-3xl p-4">
              <h2 className="font-semibold capitalize">{name}</h2>
              <ul className="mt-2 space-y-2 text-xs text-zinc-300">
                {rows.length === 0 && <li>No rows.</li>}
                {rows.map((row) => (
                  <li key={`${name}-${row.row}`} className="rounded-2xl border border-white/10 px-3 py-2">
                    <p>Row {row.row}: {row.status}{row.message ? ` — ${row.message}` : ""}</p>
                    <p className="mt-1 text-zinc-400">
                      {Object.entries(row.values).map(([key, value]) => `${key}: ${value ?? ""}`).join(" · ")}
                    </p>
                  </li>
                ))}
              </ul>
            </div>
          ))}
          <button
            type="button"
            disabled={busy || preview.error_count > 0}
            onClick={confirm}
            className="min-h-11 w-full rounded-full bg-white font-semibold text-black disabled:opacity-40"
          >
            Confirm import
          </button>
        </section>
      )}
      {result && <p className="mt-4 text-sm text-zinc-200">{result}</p>}
    </OwnerShell>
  );
}
