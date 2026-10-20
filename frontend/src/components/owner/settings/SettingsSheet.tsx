"use client";
import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import api from "@/lib/api";
import { HEADLINE_SETTINGS, formatSetting, type SettingField, type SettingsPayload, type SettingsPreview } from "@/lib/owner/settings";

type Props = {
  sheet: { kind: "one"; key: string } | { kind: "targets" };
  fields: Record<string, SettingField>;
  onClose: () => void;
  onSaved: (next: SettingsPayload) => void;
};

const PREVIEW_DELAY_MS = 350;

/** What an answer from the server says went wrong, in the owner's words. */
function problem(err: unknown): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (detail && typeof detail === "object" && "message" in detail) return String((detail as { message: string }).message);
  return "That could not be saved. Please try again.";
}

/** A bottom sheet on a phone, a centred card on a desk. Escape or a tap outside closes it. */
export default function SettingsSheet({ sheet, fields, onClose, onSaved }: Props) {
  const keys = sheet.kind === "one" ? [sheet.key] : HEADLINE_SETTINGS.filter((k) => fields[k]);
  const [draft, setDraft] = useState<Record<string, number>>(() => Object.fromEntries(keys.map((k) => [k, fields[k].value])));
  const [preview, setPreview] = useState<{ state: "idle" | "loading" | "ready" | "failed"; data?: SettingsPreview }>({ state: "idle" });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const first = useRef<HTMLInputElement>(null);
  const latest = useRef(0);

  useEffect(() => { first.current?.focus(); }, []);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const changed = Object.fromEntries(keys.filter((k) => draft[k] !== fields[k].value).map((k) => [k, draft[k]]));
  const invalid = keys.some((k) => !Number.isFinite(draft[k]) || draft[k] < fields[k].min || draft[k] > fields[k].max);
  const hasChange = Object.keys(changed).length > 0;
  const changeKey = JSON.stringify(changed);

  // What would change, asked of the real engines after the owner stops moving the slider; a slow answer to an old position is ignored.
  useEffect(() => {
    if (sheet.kind !== "one" || !hasChange || invalid) { latest.current += 1; return; }
    const id = ++latest.current;
    const timer = window.setTimeout(() => {
      setPreview({ state: "loading" });
      api.post<SettingsPreview>("/api/v1/owner/settings/preview", JSON.parse(changeKey))
        .then((r) => { if (id === latest.current) setPreview({ state: "ready", data: r.data }); })
        .catch(() => { if (id === latest.current) setPreview({ state: "failed" }); });
    }, PREVIEW_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [sheet.kind, hasChange, invalid, changeKey]);

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      // First run saves every answer shown, even the ones left at the usual: that is what records "you chose your targets".
      const body = sheet.kind === "targets" ? Object.fromEntries(keys.map((k) => [k, draft[k]])) : changed;
      const res = await api.put<SettingsPayload>("/api/v1/owner/settings", body);
      onSaved(res.data);
    } catch (e) {
      setError(problem(e));
    } finally {
      setSaving(false);
    }
  };

  const title = sheet.kind === "one" ? fields[sheet.key].label : "Your targets";
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 sm:items-center" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-labelledby="settings-title" onClick={(e) => e.stopPropagation()}
        className="vibanda-theme owner-theme max-h-[90vh] w-full overflow-y-auto rounded-t-2xl bg-[var(--v-card)] p-5 shadow-xl sm:max-w-lg sm:rounded-2xl">
        <div className="mb-3 flex items-start justify-between gap-3">
          <div>
            <h2 id="settings-title" className="font-display text-xl font-semibold tracking-[-0.03em]">{title}</h2>
            {sheet.kind === "targets" && <p className="mt-1 text-xs text-[var(--v-muted-foreground)]">We have filled in the answers most restaurants give. Change any that are not right for yours.</p>}
          </div>
          <button type="button" aria-label="Close" onClick={onClose} className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg hover:bg-[var(--v-muted)]"><X size={18} /></button>
        </div>

        <div className="space-y-6">
          {keys.map((k, i) => {
            const f = fields[k];
            const v = draft[k];
            return (
              <div key={k}>
                <label htmlFor={`set-${k}`} className="block text-sm font-semibold leading-snug">{f.question}</label>
                <div className="mt-3 flex items-center gap-3">
                  <input aria-label={`${f.label}, slider`} type="range" min={f.min} max={f.max} step={f.step} value={Number.isFinite(v) ? v : f.value}
                    onChange={(e) => setDraft((d) => ({ ...d, [k]: Number(e.target.value) }))} className="h-2 w-full flex-1 accent-[var(--v-primary)]" />
                  <input id={`set-${k}`} ref={i === 0 ? first : undefined} type="number" inputMode="decimal" min={f.min} max={f.max} step={f.step} value={Number.isFinite(v) ? v : ""}
                    onChange={(e) => setDraft((d) => ({ ...d, [k]: e.target.value === "" ? NaN : Number(e.target.value) }))}
                    className="h-10 w-24 rounded-lg border border-[var(--v-border)] bg-[var(--v-bg)] px-2 text-right text-sm tabular-nums" />
                  <span className="w-14 text-xs text-[var(--v-muted-foreground)]">{f.unit}</span>
                </div>
                <div className="mt-1.5 flex flex-wrap items-center justify-between gap-2 text-[11px] text-[var(--v-muted-foreground)]">
                  <span>Allowed: {formatSetting(f, f.min)} to {formatSetting(f, f.max)}</span>
                  {v !== f.default && <button type="button" onClick={() => setDraft((d) => ({ ...d, [k]: f.default }))} className="min-h-8 font-semibold text-[var(--v-primary)]">Use our usual: {formatSetting(f, f.default)}</button>}
                </div>
                {f.hint && <p className="mt-1 text-[11px] leading-relaxed text-[var(--v-muted-foreground)]">{f.hint}</p>}
                {(!Number.isFinite(v) || v < f.min || v > f.max) && <p role="alert" className="mt-1 text-[11px] font-semibold text-[var(--v-destructive)]">Choose a number from {f.min} to {f.max}.</p>}
              </div>
            );
          })}
        </div>

        {sheet.kind === "one" && (
          <div aria-live="polite" className="mt-5 min-h-[3rem] rounded-lg bg-[var(--v-muted)] px-3 py-2 text-xs">
            {!hasChange && <span className="text-[var(--v-muted-foreground)]">Move the slider to see what it would change on Home.</span>}
            {hasChange && !invalid && preview.state === "loading" && <span className="text-[var(--v-muted-foreground)]">Checking what would change…</span>}
            {hasChange && preview.state === "failed" && <span className="text-[var(--v-muted-foreground)]">We could not check that just now. You can still save it.</span>}
            {hasChange && !invalid && preview.state === "ready" && preview.data && <PreviewLine p={preview.data} />}
          </div>
        )}

        {error && <p role="alert" className="mt-3 text-xs font-semibold text-[var(--v-destructive)]">{error}</p>}
        <div className="mt-5 flex flex-wrap justify-end gap-2">
          <button type="button" onClick={onClose} className="min-h-11 rounded-lg border border-[var(--v-border)] px-4 text-sm font-semibold">{sheet.kind === "targets" ? "Not now" : "Cancel"}</button>
          <button type="button" disabled={saving || invalid || (sheet.kind === "one" && !hasChange)} onClick={save}
            className="min-h-11 rounded-lg bg-[var(--v-primary)] px-4 text-sm font-bold text-[var(--v-primary-foreground)] disabled:opacity-50">
            {saving ? "Saving…" : sheet.kind === "targets" ? "These are right" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}

function PreviewLine({ p }: { p: SettingsPreview }) {
  if (p.changed === 0) return <span>Nothing on Home would change.</span>;
  const parts = [
    p.appear.length ? `${p.appear.length} ${p.appear.length === 1 ? "idea would appear" : "ideas would appear"}` : "",
    p.disappear.length ? `${p.disappear.length} ${p.disappear.length === 1 ? "would go away" : "would go away"}` : "",
    p.figures.length ? `${p.figures.length} ${p.figures.length === 1 ? "would change its figure" : "would change their figures"}` : "",
  ].filter(Boolean);
  return (
    <div>
      <p className="font-semibold">{p.changed} {p.changed === 1 ? "card" : "cards"} on Home would change: {parts.join(", ")}.</p>
      <ul className="mt-1 list-disc space-y-0.5 pl-4 text-[var(--v-muted-foreground)]">{[...p.appear, ...p.disappear, ...p.figures].slice(0, 4).map((s) => <li key={s}>{s}</li>)}</ul>
    </div>
  );
}
