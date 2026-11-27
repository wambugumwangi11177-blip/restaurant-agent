import { NextResponse } from "next/server";
import release from "@/lib/leviii-store-version.json";

export const dynamic = "force-dynamic";

const TEST_APK_URL =
  "https://github.com/wambugumwangi11177-blip/restaurant-agent/releases/download/leviii-store-test/LEVIII-Store-Test.apk";
const TEST_APK_FILENAME = "LEVIII-Store-Test.apk";

export function androidReleaseForRequest(request: Request) {
  const overrideUrl = process.env.LEVIII_ANDROID_APK_URL?.trim();
  const host = request.headers.get("host") ?? "";
  if (overrideUrl) {
    return {
      ...release.android,
      url: overrideUrl,
      filename:
        process.env.LEVIII_ANDROID_APK_FILENAME?.trim() ||
        overrideUrl.split("/").pop() ||
        release.android.filename,
    };
  }
  if (host.includes("frontend-test")) {
    return { ...release.android, url: TEST_APK_URL, filename: TEST_APK_FILENAME };
  }
  return release.android;
}

export function GET(request: Request) {
  return NextResponse.json(
    { ...release, android: androidReleaseForRequest(request) },
    { headers: { "Cache-Control": "no-store" } },
  );
}
