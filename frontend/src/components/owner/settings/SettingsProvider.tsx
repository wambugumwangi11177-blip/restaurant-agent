"use client";
/**
 * The owner's settings, available wherever a number says "based on your …" (docs/v2/SPEC.md §3.2): one fetch for the whole shell, one
 * sheet that opens on a single setting (from a "Based on" chip) or on the first-run questions (onboarding "Your targets").
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import api from "@/lib/api";
import type { SettingField, SettingsPayload } from "@/lib/owner/settings";
import SettingsSheet from "./SettingsSheet";

export const SETTINGS_CHANGED = "owner-settings-changed";

type Sheet = { kind: "one"; key: string } | { kind: "targets" } | null;

type Value = {
  /** null until loaded, or when the settings cannot be read (the chips then show the rule without a way to change it) */
  fields: Record<string, SettingField> | null;
  chosen: boolean | null;
  openSetting: (key: string) => void;
  openTargets: () => void;
};

const Ctx = createContext<Value>({ fields: null, chosen: null, openSetting: () => {}, openTargets: () => {} });
export const useSettings = () => useContext(Ctx);

export default function SettingsProvider({ children }: { children: ReactNode }) {
  const [payload, setPayload] = useState<SettingsPayload | null>(null);
  const [sheet, setSheet] = useState<Sheet>(null);

  useEffect(() => {
    let live = true;
    api.get<SettingsPayload>("/api/v1/owner/settings").then((r) => { if (live) setPayload(r.data); }).catch(() => {});
    return () => { live = false; };
  }, []);

  const fields = useMemo(() => (payload ? Object.fromEntries(payload.fields.map((f) => [f.key, f])) : null), [payload]);
  const saved = useCallback((next: SettingsPayload) => {
    setPayload(next);
    setSheet(null);
    window.dispatchEvent(new Event(SETTINGS_CHANGED));              // Home re-asks: its cards and figures moved
  }, []);
  const value = useMemo<Value>(() => ({
    fields, chosen: payload ? payload.chosen : null,
    openSetting: (key) => { if (fields?.[key]) setSheet({ kind: "one", key }); },
    openTargets: () => { if (fields) setSheet({ kind: "targets" }); },
  }), [fields, payload]);

  return (
    <Ctx.Provider value={value}>
      {children}
      {sheet && fields && <SettingsSheet sheet={sheet} fields={fields} onClose={() => setSheet(null)} onSaved={saved} />}
    </Ctx.Provider>
  );
}
