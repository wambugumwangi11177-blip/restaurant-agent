// Authenticated proxy: /api/os/<path> -> BACKEND_URL/api/v1/<path>, adding the
// bearer token from the httpOnly session cookie.
import { NextRequest, NextResponse } from "next/server";
import { BACKEND_URL, SESSION_COOKIE, sameOrigin } from "@/lib/server";

type Ctx = { params: Promise<{ path: string[] }> };

async function handle(req: NextRequest, ctx: Ctx) {
  const { path } = await ctx.params;
  if (path.some((s) => s === "." || s === ".." || s === "")) {
    return NextResponse.json({ detail: "Bad path" }, { status: 400 });
  }
  if (req.method !== "GET" && !sameOrigin(req)) {
    return NextResponse.json({ detail: "Cross-origin request refused" }, { status: 403 });
  }
  const token = req.cookies.get(SESSION_COOKIE)?.value;
  if (!token) return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });

  const headers: Record<string, string> = { authorization: `Bearer ${token}` };
  const contentType = req.headers.get("content-type");
  if (contentType) headers["content-type"] = contentType;
  const requestId = req.headers.get("x-request-id");
  if (requestId) headers["x-request-id"] = requestId;

  const url = `${BACKEND_URL}/api/v1/${path.map(encodeURIComponent).join("/")}${req.nextUrl.search}`;
  let upstream: Response;
  try {
    upstream = await fetch(url, {
      method: req.method,
      headers,
      body: req.method === "GET" ? undefined : await req.arrayBuffer(),
      cache: "no-store",
    });
  } catch {
    return NextResponse.json({ detail: "The Company OS API is unreachable" }, { status: 502 });
  }
  const body = upstream.status === 204 ? null : await upstream.arrayBuffer();
  const res = new NextResponse(body, { status: upstream.status });
  const upstreamType = upstream.headers.get("content-type");
  if (upstreamType) res.headers.set("content-type", upstreamType);
  const rid = upstream.headers.get("x-request-id");
  if (rid) res.headers.set("x-request-id", rid);
  if (upstream.status === 401) res.cookies.delete(SESSION_COOKIE);
  return res;
}

export { handle as GET, handle as POST, handle as PATCH, handle as PUT, handle as DELETE };
