import { NextRequest, NextResponse } from "next/server";
import { BACKEND_URL, SESSION_COOKIE, sameOrigin } from "@/lib/server";

export async function POST(req: NextRequest) {
  if (!sameOrigin(req)) return NextResponse.json({ detail: "Cross-origin request refused" }, { status: 403 });
  const r = await fetch(`${BACKEND_URL}/api/v1/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: await req.text(),
    cache: "no-store",
  });
  const data = await r.json().catch(() => ({ detail: "The API returned an unreadable response" }));
  if (!r.ok) return NextResponse.json(data, { status: r.status });
  const res = NextResponse.json({ ok: true });
  res.cookies.set(SESSION_COOKIE, data.access_token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: Number(data.expires_in) || 3600,
  });
  return res;
}

export async function DELETE(req: NextRequest) {
  if (!sameOrigin(req)) return NextResponse.json({ detail: "Cross-origin request refused" }, { status: 403 });
  const res = NextResponse.json({ ok: true });
  res.cookies.delete(SESSION_COOKIE);
  return res;
}
