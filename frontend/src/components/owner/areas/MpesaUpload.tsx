"use client";
// Upload the M-Pesa statement the owner exports, see what was read and what was not, and take an upload back (backend/routers/owner_mpesa.py).
// Nothing here guesses: a row we could not read is listed with its row number and why, so the owner knows exactly what the check rests on.
import { useCallback, useEffect, useRef, useState } from "react";
import api from "@/lib/api";
import { OWNER_DATA_CHANGED } from "@/lib/owner/useOwnerHome";
import { kes, shortDay } from "@/lib/owner/format";
import { Note } from "./ui";

type Upload = { id: number; filename: string; uploaded_at: string; lines: number; from: string | null; to: string | null; uploaded_by: string | null };
type Result = {
  upload: Upload | null; new: number; already_uploaded: number; not_read: { row: number; reason: string }[]; not_read_count: number;
  money_in_kes: number; money_out_kes: number; about: Record<string, string>;
};

const day = (iso: string | null) => (iso ? shortDay(new Date(new Date(iso).getTime() + 3 * 3600_000).toISOString().slice(0, 10)) : "");

function errorWords(e: unknown): string {
  const detail = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  return typeof detail === "string" ? detail : "We could not upload that file just now. Check your connection and try again.";
}

export default function MpesaUpload() {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [files, setFiles] = useState<Upload[]>([]);
  const [onFile, setOnFile] = useState(0);
  const [removing, setRemoving] = useState<number | null>(null);

  const refresh = useCallback(async () => {
    try {
      const r = await api.get<{ statements: Upload[]; payments_on_file: number }>("/api/v1/owner/mpesa/statements");
      if (Array.isArray(r.data?.statements)) { setFiles(r.data.statements); setOnFile(r.data.payments_on_file ?? 0); }
    } catch { /* the list is a convenience; the upload still works without it */ }
  }, []);
  // The list is fetched once on arrival; the request is the external synchronisation this effect performs.
  useEffect(() => { void refresh(); }, [refresh]);

  const changed = () => { void refresh(); window.dispatchEvent(new Event(OWNER_DATA_CHANGED)); };

  async function send(file: File) {
    setBusy(true); setError(null); setResult(null);
    const form = new FormData();
    form.append("file", file);
    try {
      const r = await api.post<Result>("/api/v1/owner/mpesa/statement", form, { headers: { "Content-Type": "multipart/form-data" }, timeout: 60000 });
      setResult(r.data);
      changed();
    } catch (e) { setError(errorWords(e)); }
    finally { setBusy(false); if (input.current) input.current.value = ""; }
  }

  async function remove(id: number) {
    setRemoving(id); setError(null);
    try { await api.delete(`/api/v1/owner/mpesa/statements/${id}`); setResult(null); changed(); }
    catch (e) { setError(errorWords(e)); }
    finally { setRemoving(null); }
  }

  return (
    <section aria-label="Your M-Pesa statement" className="rounded-lg border border-dashed border-[var(--v-border)] p-3.5 sm:p-4">
      <h4 className="text-[11px] font-bold uppercase tracking-[0.12em] text-[var(--v-muted-foreground)]">Your M-Pesa statement</h4>
      <p className="mt-1.5 text-xs leading-relaxed text-[var(--v-muted-foreground)]">
        Export the transaction report from M-Pesa as a CSV file and upload it here. We only read it, to check each payment against a sale. Upload the same period twice and nothing is counted twice.
      </p>
      <div className="mt-2.5">
        <input ref={input} id="mpesa-statement" type="file" accept=".csv,text/csv" className="sr-only" disabled={busy}
          onChange={(e) => { const f = e.target.files?.[0]; if (f) void send(f); }} />
        <label htmlFor="mpesa-statement" className={`inline-flex min-h-10 cursor-pointer items-center rounded-lg border border-[var(--v-border)] px-3 text-xs font-bold ${busy ? "opacity-60" : "hover:border-[var(--v-primary)]"}`}>
          {busy ? "Reading your statement…" : "Choose a statement (CSV)"}
        </label>
      </div>

      {error && <p role="alert" className="mt-2.5 rounded-lg bg-[hsl(4_61%_52%_/_0.1)] px-3 py-2 text-xs text-[var(--v-destructive)]">{error}</p>}

      {result && (
        <div role="status" className="mt-2.5 rounded-lg bg-[var(--v-muted)] px-3 py-2 text-xs">
          <p className="font-semibold">
            {result.new > 0
              ? `Read ${result.new} new payment${result.new === 1 ? "" : "s"} from ${result.upload?.filename ?? "your file"} (${kes(result.money_in_kes)} in${result.money_out_kes ? `, ${kes(result.money_out_kes)} out` : ""}).`
              : "Every payment in this file was already uploaded, so nothing changed."}
            {result.already_uploaded > 0 && result.new > 0 ? ` ${result.already_uploaded} were already on file.` : ""}
          </p>
          {result.not_read_count > 0 && (
            <details className="mt-1.5">
              <summary className="min-h-10 cursor-pointer py-2 font-semibold">{result.not_read_count} row{result.not_read_count === 1 ? " was" : "s were"} not read</summary>
              <ul className="space-y-0.5 pb-1">
                {result.not_read.map((n) => <li key={n.row}>Row {n.row}: {n.reason}</li>)}
              </ul>
              {result.not_read_count > result.not_read.length && <p>and {result.not_read_count - result.not_read.length} more.</p>}
            </details>
          )}
        </div>
      )}

      {files.length > 0 && (
        <details className="mt-2.5 text-xs">
          <summary className="min-h-10 cursor-pointer py-2 font-semibold">{onFile} payment{onFile === 1 ? "" : "s"} on file from {files.length} upload{files.length === 1 ? "" : "s"}</summary>
          <ul className="space-y-1.5 pb-1">
            {files.map((f) => (
              <li key={f.id} className="flex items-center justify-between gap-3">
                <span className="min-w-0 truncate">{f.filename} · {f.lines} payment{f.lines === 1 ? "" : "s"}{f.from ? ` · ${day(f.from)} to ${day(f.to)}` : ""}</span>
                <button type="button" onClick={() => void remove(f.id)} disabled={removing === f.id}
                  className="min-h-10 shrink-0 rounded-lg border border-[var(--v-border)] px-3 text-[11px] font-bold hover:border-[var(--v-destructive)]">
                  {removing === f.id ? "Removing…" : "Remove this upload"}
                </button>
              </li>
            ))}
          </ul>
          <Note>Removing an upload takes its payments out of the check. Your sales are not touched.</Note>
        </details>
      )}
    </section>
  );
}
