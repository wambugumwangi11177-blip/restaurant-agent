"use client";
// A short AI-written note on Home and Reports (ADR 0007). The text comes from a
// creative (temperature > 0) model that may only cite figures already in the
// evidence it was given; this component's job is to show it honestly:
//   • labelled as AI-written, with what kind of statement it is,
//   • stamped with when it was written (it is cached, so it can lag the cards),
//   • never blocking or breaking the page — it renders nothing at all unless
//     the server returned real text, so a malformed, empty or failed response
//     simply leaves the page as it was.
import { useCallback, useEffect, useRef, useState } from "react";
import { RefreshCw, Sparkles } from "lucide-react";
import api from "@/lib/api";

type Payload = {
  mode?: string;
  text?: unknown;
  stale?: boolean;
  generated_at?: string | null;
  reason?: string | null;
  refresh_failed?: boolean;
};

const COPY: Record<string, { eyebrow: string; disclaimer: string }> = {
  today_story: {
    eyebrow: "Today’s story · AI-written",
    disclaimer: "From your verified figures; ideas are suggestions to test.",
  },
  system_story: {
    eyebrow: "About your Restaurant OS · AI-written",
    disclaimer: "Describes the software, not your results.",
  },
  report_take: {
    eyebrow: "Creative take · AI-written",
    disclaimer: "An idea to test, not a verified finding.",
  },
};
const FALLBACK_COPY = { eyebrow: "AI-written", disclaimer: "Ideas are suggestions to test." };

// Why the last attempt to write a NEW version failed. Other reasons (disabled,
// no data, ungrounded output…) are not the owner's concern, so they say nothing.
const FAILURE_NOTE: Record<string, string> = {
  budget_reached: "Today’s AI budget is used up, so this is the last note that was written.",
  provider_error: "A fresh note couldn’t be written just now, so this is the last one that was.",
};

const TIMEOUT_MS = 45000;

// Backend timestamps are naive UTC (see time_utils.py); "Z" makes the browser
// read them as UTC before converting to the restaurant's zone.
function writtenAt(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const date = new Date(iso.endsWith("Z") ? iso : `${iso}Z`);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleTimeString("en-KE", {
    timeZone: "Africa/Nairobi", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  });
}

function withRefresh(endpoint: string): string {
  return `${endpoint}${endpoint.includes("?") ? "&" : "?"}refresh=1`;
}

const hasText = (data: Payload | null | undefined): data is Payload & { text: string } =>
  typeof data?.text === "string" && data.text.trim().length > 0;

export default function CreativeNote({ endpoint, className = "" }: { endpoint: string; className?: string }) {
  // Keyed by endpoint so switching period never shows the previous period's text,
  // and so nothing needs resetting synchronously inside the effect.
  const [loaded, setLoaded] = useState<{ endpoint: string; data: Payload | null }>({ endpoint: "", data: null });
  const [busy, setBusy] = useState(false);
  const [refreshError, setRefreshError] = useState(false);
  const requestId = useRef(0);

  useEffect(() => {
    const id = ++requestId.current;
    api.get<Payload>(endpoint, { timeout: TIMEOUT_MS })
      .then((response) => {
        if (id !== requestId.current) return;
        const data = response.data ?? null;
        setLoaded({ endpoint, data });
        // Stale text is shown at once, then refreshed once in the background.
        // A response whose own refresh just failed is not retried: that would
        // hammer a provider that is already refusing.
        if (hasText(data) && data.stale === true && data.refresh_failed !== true) {
          api.get<Payload>(withRefresh(endpoint), { timeout: TIMEOUT_MS })
            .then((next) => {
              if (id === requestId.current && hasText(next.data)) setLoaded({ endpoint, data: next.data });
            })
            .catch(() => { /* The stale text stays; its timestamp says how old it is. */ });
        }
      })
      .catch(() => { if (id === requestId.current) setLoaded({ endpoint, data: null }); });
    return () => { requestId.current += 1; };
  }, [endpoint]);

  const tryAnother = useCallback(() => {
    const id = requestId.current;
    setBusy(true);
    setRefreshError(false);
    api.get<Payload>(withRefresh(endpoint), { timeout: TIMEOUT_MS })
      .then((response) => {
        if (id !== requestId.current) return;
        if (hasText(response.data)) setLoaded({ endpoint, data: response.data });
        else setRefreshError(true);
      })
      .catch(() => { if (id === requestId.current) setRefreshError(true); })
      .finally(() => { if (id === requestId.current) setBusy(false); });
  }, [endpoint]);

  const data = loaded.endpoint === endpoint ? loaded.data : null;
  if (!hasText(data)) return null;

  const copy = COPY[data.mode ?? ""] ?? FALLBACK_COPY;
  const time = writtenAt(data.generated_at);
  const failure = data.refresh_failed === true ? FAILURE_NOTE[data.reason ?? ""] : undefined;

  return (
    <section
      aria-live="polite"
      aria-label={copy.eyebrow}
      className={`rounded-xl border border-[hsl(43_76%_57_/_0.45)] bg-[hsl(42_71%_75_/_0.16)] p-4 ${className}`}
    >
      <p className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.15em] text-[var(--v-muted-foreground)]">
        <Sparkles size={12} className="text-[var(--v-primary)]" aria-hidden="true" />
        {copy.eyebrow}
      </p>
      <p className="mt-2 whitespace-pre-wrap text-[13px] leading-relaxed text-[hsl(208_29%_19_/_0.92)]">{data.text}</p>
      <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-[var(--v-muted-foreground)]">
        <span>{copy.disclaimer}</span>
        {time && <span>Written {time}</span>}
        <button
          type="button"
          onClick={tryAnother}
          disabled={busy}
          className="inline-flex min-h-8 items-center gap-1 rounded-lg border border-[var(--v-border)] px-2 py-1 font-bold text-[var(--v-primary)] transition-colors hover:bg-[var(--v-muted)] disabled:opacity-60"
        >
          <RefreshCw size={11} className={busy ? "animate-spin" : ""} aria-hidden="true" />
          {busy ? "Writing another take…" : "Try another take"}
        </button>
      </div>
      {(failure || refreshError) && (
        <p className="mt-1 text-[10px] text-[var(--v-muted-foreground)]">
          {refreshError ? "A new take couldn’t be written just now." : failure}
        </p>
      )}
    </section>
  );
}
