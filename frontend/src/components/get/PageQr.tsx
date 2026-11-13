"use client";

import { useEffect, useState } from "react";
import QRCode from "qrcode";

export function PageQr({ url }: { url: string }) {
  const [svg, setSvg] = useState("");

  useEffect(() => {
    let live = true;
    QRCode.toString(url, {
      type: "svg",
      margin: 1,
      color: { dark: "#111111", light: "#ffffff" },
    })
      .then((markup) => {
        if (live) setSvg(markup);
      })
      .catch(() => {
        if (live) setSvg("");
      });
    return () => {
      live = false;
    };
  }, [url]);

  return (
    <div className="owner-glass-panel rounded-3xl p-4">
      <p className="text-sm font-semibold">Scan from a phone</p>
      <p className="mt-1 text-xs leading-5 text-zinc-400">This code opens this same page.</p>
      {svg ? (
        <div
          className="mx-auto mt-3 w-44 rounded-2xl bg-white p-2 [&_svg]:h-auto [&_svg]:w-full"
          role="img"
          aria-label={`QR code for ${url}`}
          dangerouslySetInnerHTML={{ __html: svg }}
        />
      ) : (
        <div className="mx-auto mt-3 h-44 w-44 rounded-2xl bg-white/10" aria-hidden />
      )}
    </div>
  );
}
