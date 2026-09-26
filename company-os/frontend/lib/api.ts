// Browser-side API client. Every call goes through the same-origin BFF proxy.
export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

type PydanticError = { loc?: (string | number)[]; msg?: string };

function describe(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return (detail as PydanticError[])
      .map((e) => `${(e.loc ?? []).filter((p) => p !== "body").join(".")}: ${e.msg ?? "invalid"}`)
      .join("; ");
  }
  if (detail && typeof detail === "object" && "message" in detail) return String((detail as { message: unknown }).message);
  return "Something went wrong";
}

export async function api<T = unknown>(
  path: string,
  opts: { method?: string; body?: unknown; form?: FormData } = {},
): Promise<T> {
  const init: RequestInit = { method: opts.method ?? (opts.body || opts.form ? "POST" : "GET") };
  if (opts.form) init.body = opts.form;
  else if (opts.body !== undefined) {
    init.body = JSON.stringify(opts.body);
    init.headers = { "content-type": "application/json" };
  }
  const r = await fetch(`/api/os/${path.replace(/^\//, "")}`, init);
  if (r.status === 401 && typeof window !== "undefined" && window.location.pathname !== "/login") {
    window.location.href = "/login";
  }
  if (r.status === 204) return undefined as T;
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new ApiError(r.status, describe((data as { detail?: unknown }).detail));
  return data as T;
}

export function fmtDate(iso: string | null | undefined, timeZone = "Africa/Nairobi"): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat("en-KE", { dateStyle: "medium", timeStyle: iso.length > 10 ? "short" : undefined, timeZone }).format(d);
}

/** Money for LLM costs: 4 decimals below one dollar (runs cost fractions of a cent), 2 above. */
export function usd(value: string | number): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value);
  return `$${n < 1 ? n.toFixed(4) : n.toFixed(2)}`;
}
