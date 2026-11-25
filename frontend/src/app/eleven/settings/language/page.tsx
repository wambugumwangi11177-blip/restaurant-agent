"use client";

import { useEffect, useState } from "react";
import OwnerShell from "@/components/eleven/OwnerShell";
import api from "@/lib/api";

export default function SettingsLanguagePage() {
  const [locale, setLocale] = useState("en");
  const [msg, setMsg] = useState("");

  useEffect(() => {
    api.get("/api/v1/eleven/settings/targets").then((r) => setLocale(r.data.locale || "en"));
  }, []);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    await api.patch("/api/v1/eleven/settings/targets", { locale });
    setMsg(locale === "sw" ? "Swahili stub saved — English remains default UI." : "English saved.");
  }

  return (
    <OwnerShell title="Language">
      <form onSubmit={save} className="owner-glass-panel space-y-4 p-5">
        <label className="block text-sm">
          App language
          <select className="mt-1 w-full rounded-2xl border border-white/15 bg-black/30 px-3 py-2" value={locale} onChange={(e) => setLocale(e.target.value)}>
            <option value="en">English</option>
            <option value="sw">Swahili (stub)</option>
          </select>
        </label>
        <button type="submit" className="leviii-btn-primary px-4 py-2">Save</button>
        {msg && <p className="text-sm text-zinc-300">{msg}</p>}
      </form>
    </OwnerShell>
  );
}