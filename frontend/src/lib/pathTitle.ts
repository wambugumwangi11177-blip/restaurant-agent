/**
 * pathTitle — derive a browser-tab title from the current pathname using the
 * sidebar's own nav labels (single source of truth), so every page — owner
 * and every staff tier — gets "POS · Chakula"-style titles without hand
 * editing 60+ page files. Longest-href-prefix match wins, so nested routes
 * (/dashboard/ai/revenue) resolve to their section label ("AI").
 */
export function labelForPath(pathname: string, pairs: { href: string; label: string }[]): string {
    let bestHref = "";
    let bestLabel = "";
    for (const p of pairs) {
        const isMatch = pathname === p.href || pathname.startsWith(p.href + "/");
        if (isMatch && p.href.length > bestHref.length) {
            bestHref = p.href;
            bestLabel = p.label;
        }
    }
    if (bestLabel) return bestLabel;
    // Not a nav route (e.g. a modal-less sub-page) — fall back to a tidy
    // rendering of the last path segment ("ai-ops" → "Ai Ops").
    const seg = pathname.split("/").filter(Boolean).pop() || "Dashboard";
    return seg
        .split("-")
        .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
        .join(" ");
}
