"use client";

import { useEffect } from "react";
import { registerLeviiiServiceWorker } from "@/lib/swCleanup";

export default function ServiceWorkerRegister() {
  useEffect(() => {
    registerLeviiiServiceWorker();
  }, []);
  return null;
}