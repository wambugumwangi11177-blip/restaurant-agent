"use client";

import { useEffect, useState } from "react";
import { GetInstall } from "@/components/get/GetInstall";
import { resolveInstallDevice, type InstallDevice } from "@/lib/installDevice";

export default function GetPage() {
  const [device, setDevice] = useState<InstallDevice | "unknown">("unknown");
  const [picked, setPicked] = useState(false);
  const [pageUrl, setPageUrl] = useState("https://frontend-production-e251.up.railway.app/get");

  useEffect(() => {
    setPageUrl(window.location.origin + "/get");
    let live = true;
    resolveInstallDevice().then((found) => {
      if (live && !picked) setDevice(found);
    });
    return () => {
      live = false;
    };
  }, [picked]);

  return (
    <GetInstall
      device={device}
      pageUrl={pageUrl}
      onDevice={(next) => {
        setPicked(true);
        setDevice(next);
      }}
    />
  );
}
