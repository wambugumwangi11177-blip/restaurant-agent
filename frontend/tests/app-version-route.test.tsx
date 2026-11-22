import { afterEach, expect, it } from "vitest";
import { androidReleaseForRequest } from "@/app/api/app/version/route";
import release from "@/lib/leviii-store-version.json";

const PROD =
  "https://github.com/wambugumwangi11177-blip/restaurant-agent/releases/download/leviii-store/LEVIII-Store.apk";
const TEST =
  "https://github.com/wambugumwangi11177-blip/restaurant-agent/releases/download/leviii-store-test/LEVIII-Store-Test.apk";

afterEach(() => {
  delete process.env.LEVIII_ANDROID_APK_URL;
  delete process.env.LEVIII_ANDROID_APK_FILENAME;
});

it("keeps the production APK URL on a normal host", () => {
  const android = androidReleaseForRequest(new Request("https://frontend-production.up.railway.app/api/app/version", {
    headers: { host: "frontend-production-xxxx.up.railway.app" },
  }));
  expect(android.url).toBe(PROD);
  expect(android.url).toBe(release.android.url);
  expect(android.filename).toBe("LEVIII-Store.apk");
});

it("serves the test APK on a frontend-test host", () => {
  const android = androidReleaseForRequest(new Request("https://frontend-test-production-752b1b7c.up.railway.app/api/app/version", {
    headers: { host: "frontend-test-production-752b1b7c.up.railway.app" },
  }));
  expect(android.url).toBe(TEST);
  expect(android.filename).toBe("LEVIII-Store-Test.apk");
});

it("lets LEVIII_ANDROID_APK_URL override the file, including filename", () => {
  process.env.LEVIII_ANDROID_APK_URL = TEST;
  const android = androidReleaseForRequest(new Request("https://example.com/api/app/version", {
    headers: { host: "example.com" },
  }));
  expect(android.url).toBe(TEST);
  expect(android.filename).toBe("LEVIII-Store-Test.apk");
});
