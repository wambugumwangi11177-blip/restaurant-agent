"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";

export default function AuthPhotoThumb({
  path,
  className = "h-16 w-16 rounded-lg object-cover ring-1 ring-white/10",
  largeClassName = "mt-2 max-h-40 rounded-xl border border-white/10",
  large,
}: {
  path: string;
  className?: string;
  largeClassName?: string;
  large?: boolean;
}) {
  const [src, setSrc] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setSrc(null);
    api
      .get(path, { responseType: "blob" })
      .then((res) => {
        if (!alive) return;
        setSrc(URL.createObjectURL(res.data));
      })
      .catch(() => {
        if (alive) setSrc(null);
      });
    return () => {
      alive = false;
    };
  }, [path]);

  if (!src) return null;

  return <img src={src} alt="" className={large ? largeClassName : className} />;
}