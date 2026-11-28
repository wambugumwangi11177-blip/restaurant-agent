import axios, { type AxiosRequestConfig } from "axios";

declare module "axios" {
  interface AxiosRequestConfig {
    /** Set on the report call itself so a failing report is never reported again. */
    skipErrorReport?: boolean;
  }
}

export type ClientErrorReport = {
  kind: "script" | "request";
  screen: string;
  message: string;
  status_code?: number;
};

const REPEAT_WINDOW_MS = 30_000;
const MAX_MESSAGE = 1000;

let send: ((report: ClientErrorReport) => Promise<unknown>) | null = null;
const lastSent = new Map<string, number>();

function report(entry: Omit<ClientErrorReport, "screen">) {
  if (!send || typeof window === "undefined") return;
  const message = entry.message.slice(0, MAX_MESSAGE);
  const key = `${entry.kind}|${entry.status_code ?? ""}|${message}`;
  const now = Date.now();
  if (now - (lastSent.get(key) ?? 0) < REPEAT_WINDOW_MS) return;
  lastSent.set(key, now);
  send({ ...entry, message, screen: window.location.pathname }).catch(() => undefined);
}

/** Called from the api client for every failed response. */
export function reportRequestFailure(error: unknown) {
  if (!axios.isAxiosError(error) || !error.response) return;
  const config: AxiosRequestConfig = error.config ?? {};
  const status = error.response.status;
  // 401 is an expired sign-in, which the api client already handles.
  if (config.skipErrorReport || status < 400 || status === 401) return;
  const detail = error.response.data?.detail;
  const reason = typeof detail === "string" ? detail : error.message;
  const path = (config.url ?? "").split("?")[0];
  report({
    kind: "request",
    message: `${(config.method ?? "get").toUpperCase()} ${path} failed (${status}): ${reason}`,
    status_code: status,
  });
}

/** Start reporting script errors and failed requests from this screen. Returns the undo. */
export function installErrorCapture(post: (report: ClientErrorReport) => Promise<unknown>): () => void {
  send = post;
  const onError = (event: ErrorEvent) => {
    report({ kind: "script", message: event.message || "Script error" });
  };
  const onRejection = (event: PromiseRejectionEvent) => {
    // Failed requests are already reported with their status.
    if (axios.isAxiosError(event.reason)) return;
    const reason = event.reason;
    report({ kind: "script", message: reason instanceof Error ? reason.message : String(reason ?? "Unhandled error") });
  };
  window.addEventListener("error", onError);
  window.addEventListener("unhandledrejection", onRejection);
  return () => {
    window.removeEventListener("error", onError);
    window.removeEventListener("unhandledrejection", onRejection);
    send = null;
  };
}
