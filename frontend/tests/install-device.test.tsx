import { expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach } from "vitest";
import { detectInstallDevice } from "@/lib/installDevice";
import { isNewerVersion, shouldOfferStoreUpdate, versionFromUserAgent } from "@/lib/storeRelease";
import { GetInstall } from "@/components/get/GetInstall";
import release from "@/lib/leviii-store-version.json";
import manifest from "../public/store-manifest.json";

afterEach(() => cleanup());

const android = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36";
const iphone = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 Version/17.5 Mobile/15E148 Safari/604.1";
const ipadOld = "Mozilla/5.0 (iPad; CPU OS 16_0 like Mac OS X) AppleWebKit/605.1.15 Version/16.0 Mobile/15E148 Safari/604.1";
const ipadOs = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/17.5 Safari/605.1.15";
const mac = ipadOs;
const windows = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36";

it("detects the device from the user agent, client hints, and iPad touch points", () => {
  expect(detectInstallDevice({ userAgent: android })).toBe("android");
  expect(detectInstallDevice({ userAgent: iphone })).toBe("iphone");
  expect(detectInstallDevice({ userAgent: ipadOld })).toBe("ipad");
  expect(detectInstallDevice({ userAgent: ipadOs, maxTouchPoints: 5 })).toBe("ipad");
  expect(detectInstallDevice({ userAgent: mac, maxTouchPoints: 0 })).toBe("mac");
  expect(detectInstallDevice({ userAgent: windows })).toBe("windows");
  expect(detectInstallDevice({ userAgent: mac, clientHintPlatform: "Android", maxTouchPoints: 0 })).toBe("android");
  expect(detectInstallDevice({ userAgent: mac, clientHintPlatform: "macOS", maxTouchPoints: 5 })).toBe("ipad");
  expect(detectInstallDevice({ userAgent: "Mozilla/5.0 (X11; Linux x86_64)", maxTouchPoints: 0 })).toBe("unknown");
});

it("offers an APK update only when the installed copy is older", () => {
  expect(isNewerVersion("1.0.1", "1.0.0")).toBe(true);
  expect(isNewerVersion("1.0.0", "1.0.0")).toBe(false);
  expect(isNewerVersion("1.2.0", "1.10.0")).toBe(false);
  expect(versionFromUserAgent("Mozilla/5.0 LEVIIIStore/1.0.0")).toBe("1.0.0");
  const offer = {
    userAgent: "Mozilla/5.0 LEVIIIStore/1.0.0",
    current: "1.0.0",
    latest: "1.1.0",
    androidUrl: release.android.url,
    androidAvailable: true,
  };
  expect(shouldOfferStoreUpdate(offer)).toBe(true);
  expect(shouldOfferStoreUpdate({ ...offer, latest: "1.0.0" })).toBe(false);
  expect(shouldOfferStoreUpdate({ ...offer, userAgent: "Mozilla/5.0", current: "1.0.0" })).toBe(false);
  expect(shouldOfferStoreUpdate({ ...offer, androidAvailable: false })).toBe(false);
});

it("gives the detected device one real action and no dead Windows button", async () => {
  render(<GetInstall device="android" pageUrl="https://restaurant.example/get" onDevice={() => {}} />);
  const download = screen.getByRole("link", { name: "Download LEVIII Store" });
  expect(download.getAttribute("href")).toBe(release.android.url);
  expect(screen.getByText(/allow installs from this source/i)).toBeTruthy();
  await waitFor(() => expect(screen.getByRole("img", { name: "QR code for https://restaurant.example/get" })).toBeTruthy());

  cleanup();
  render(<GetInstall device="windows" pageUrl="https://restaurant.example/get" onDevice={() => {}} />);
  expect(screen.getByText("The Windows installer is coming soon.")).toBeTruthy();
  expect(screen.queryByRole("link", { name: /download/i })).toBeNull();

  cleanup();
  const pick = viPick();
  render(<GetInstall device="iphone" pageUrl="https://restaurant.example/get" onDevice={pick.fn} />);
  expect(screen.getByRole("link", { name: "Add to Home Screen" }).getAttribute("href")).toBe("#install-steps");
  expect(screen.getByText(/Share button/i)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Choose another device" }));
  fireEvent.click(screen.getByRole("button", { name: "Mac" }));
  expect(pick.chosen).toBe("mac");
  expect(manifest.display).toBe("standalone");
  expect(manifest.name).toBe("LEVIII Store");
  expect(manifest.start_url).toBe("/store");
  expect(manifest.icons.length).toBeGreaterThan(0);
});

function viPick() {
  const box: { chosen?: string; fn: (device: "android" | "windows" | "iphone" | "ipad" | "mac") => void } = {
    fn: (device) => {
      box.chosen = device;
    },
  };
  return box;
}
