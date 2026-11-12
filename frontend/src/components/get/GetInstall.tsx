"use client";

import Link from "next/link";
import { useState, type ReactNode } from "react";
import release from "@/lib/leviii-store-version.json";
import { INSTALL_DEVICES, type InstallDevice } from "@/lib/installDevice";
import type { StoreRelease } from "@/lib/storeRelease";
import { PageQr } from "@/components/get/PageQr";
import {
  AllowSourceArt,
  DownloadArt,
  FullScreenArt,
  HomeScreenArt,
  InstallArt,
  ShareArt,
  SignInArt,
  SoonArt,
  StepsArt,
} from "@/components/get/InstallArt";

const STORE_RELEASE = release as StoreRelease;

function Step({ art, text }: { art: ReactNode; text: string }) {
  return (
    <li className="owner-glass-panel rounded-3xl p-3">
      {art}
      <p className="mt-2 text-sm leading-6 text-zinc-200">{text}</p>
    </li>
  );
}

function DeviceGuide({ device }: { device: InstallDevice }) {
  if (device === "android") {
    return (
      <ol className="grid gap-3 sm:grid-cols-3">
        <Step art={<DownloadArt />} text="Tap Download LEVIII Store. The file is the app." />
        <Step art={<AllowSourceArt />} text="Open the file. If Android stops you, tap Settings and allow installs from this source." />
        <Step art={<InstallArt />} text="Go back and tap Install. The app icon is LEVIII Store." />
      </ol>
    );
  }
  if (device === "windows") {
    return (
      <div className="owner-glass-panel rounded-3xl p-4 text-center">
        <SoonArt />
        <p className="mt-2 text-sm leading-6 text-zinc-200">The Windows installer is coming soon.</p>
      </div>
    );
  }
  const home = device === "mac" ? "Add to Dock" : "Add to Home Screen";
  return (
    <ol className="grid gap-3 sm:grid-cols-3">
      <Step art={<ShareArt />} text={device === "mac" ? "In Safari, open the Share menu." : "In Safari, tap the Share button."} />
      <Step art={<HomeScreenArt />} text={`Choose ${home}, then add LEVIII Store.`} />
      <Step art={<FullScreenArt />} text="Open it from the icon. It fills the screen, with no browser address bar." />
    </ol>
  );
}

export function GetInstall({
  device,
  pageUrl,
  onDevice,
}: {
  device: InstallDevice | "unknown";
  pageUrl: string;
  onDevice: (device: InstallDevice) => void;
}) {
  const [chooserOpen, setChooserOpen] = useState(device === "unknown");
  const selected = device === "unknown" ? null : device;
  const androidReady = STORE_RELEASE.android.available && STORE_RELEASE.android.url.startsWith("https://");
  const windowsReady = STORE_RELEASE.windows.available && Boolean(STORE_RELEASE.windows.url?.startsWith("https://"));

  return (
    <div className="owner-glass-theme min-h-screen px-4 py-8">
      <div className="mx-auto grid max-w-5xl gap-6 lg:grid-cols-[minmax(0,1fr)_280px] lg:items-start">
        <main className="space-y-6">
          <header>
            <p className="text-xs uppercase tracking-[0.16em] text-zinc-400">LEVIII Store</p>
            <h1 className="mt-2 text-3xl font-semibold">Get the store app</h1>
            <p className="mt-2 max-w-xl text-sm leading-6 text-zinc-300">
              For the person who receives deliveries. No prices on this phone.
            </p>
          </header>

          <section className="owner-glass-panel space-y-4 rounded-3xl p-4">
            {selected === "android" && androidReady && (
              <a
                href={STORE_RELEASE.android.url}
                className="flex min-h-14 w-full items-center justify-center rounded-full bg-white text-base font-semibold text-black"
              >
                Download LEVIII Store
              </a>
            )}
            {selected === "windows" && windowsReady && STORE_RELEASE.windows.url && (
              <a
                href={STORE_RELEASE.windows.url}
                className="flex min-h-14 w-full items-center justify-center rounded-full bg-white text-base font-semibold text-black"
              >
                Download for Windows
              </a>
            )}
            {selected && selected !== "android" && selected !== "windows" && (
              <a
                href="#install-steps"
                className="flex min-h-14 w-full items-center justify-center rounded-full bg-white text-base font-semibold text-black"
              >
                {selected === "mac" ? "Add to this Mac" : "Add to Home Screen"}
              </a>
            )}
            {selected === "windows" && !windowsReady && (
              <p className="text-lg font-semibold">Windows is coming soon</p>
            )}
            {!selected && <p className="text-lg font-semibold">Choose the device you are installing on</p>}
            <div>
              <button
                type="button"
                className="text-sm text-zinc-300 underline decoration-white/30 underline-offset-4"
                aria-expanded={chooserOpen}
                onClick={() => setChooserOpen((open) => !open)}
              >
                Choose another device
              </button>
              {chooserOpen && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {INSTALL_DEVICES.map((entry) => (
                    <button
                      key={entry.id}
                      type="button"
                      onClick={() => onDevice(entry.id)}
                      className={`min-h-11 rounded-full border px-4 text-sm font-semibold ${selected === entry.id ? "border-white bg-white text-black" : "border-white/25"}`}
                    >
                      {entry.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </section>

          <section id="install-steps" className="space-y-3">
            <h2 className="text-lg font-semibold">{selected === "android" ? "Allow the install" : selected === "windows" ? "Windows" : "Add it to this device"}</h2>
            {selected ? <DeviceGuide device={selected} /> : <p className="text-sm text-zinc-300">Pick Android, Windows, iPhone, iPad, or Mac.</p>}
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-semibold">After it is installed</h2>
            <ol className="grid gap-3 sm:grid-cols-3">
              <Step art={<FullScreenArt />} text="Open LEVIII Store." />
              <Step art={<SignInArt />} text="Sign in with the email and password the owner gave you." />
              <Step art={<StepsArt />} text="Change that password, set your own 4-digit PIN, then answer the short questions." />
            </ol>
            <Link href="/login" className="inline-flex min-h-11 items-center text-sm font-semibold text-white underline decoration-white/30 underline-offset-4">
              Open the sign-in page
            </Link>
          </section>
        </main>
        <PageQr url={pageUrl} />
      </div>
    </div>
  );
}
