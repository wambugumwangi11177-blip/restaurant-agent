"use client";
import { useSyncExternalStore } from "react";
import { useSearchParams } from "next/navigation";

function subscribe(notify: () => void) {
  window.addEventListener("hashchange", notify);
  window.addEventListener("popstate", notify);
  return () => { window.removeEventListener("hashchange", notify); window.removeEventListener("popstate", notify); };
}
/** The last fragment recovers old links such as #ingredients-and-wages#costs-covered. */
export function legacyTool(hash: string) {
  try { return decodeURIComponent(hash).split("#").filter(Boolean).at(-1) ?? ""; }
  catch { return "invalid-tool"; }
}
export function toolHref(path: string, tool: string) {
  return tool ? `${path}?tool=${encodeURIComponent(tool)}` : path;
}
export function useToolSelection() {
  const search = useSearchParams();
  const hash = useSyncExternalStore(subscribe, () => window.location.hash, () => "");
  return search.get("tool") ?? legacyTool(hash);
}
