"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";

export type ApprovalFeedItem = {
  kind: string;
  id: number;
  approval_card_title?: string;
  approval_card_subtitle?: string;
  approval_detail_bullets?: string[];
  approval_type_label?: string;
  approval_reason_line?: string | null;
  approval_when_label?: string | null;
  approval_needs_you?: boolean;
  approval_viewer_is_actor?: boolean;
  approval_waiting_on?: string | null;
  status?: string;
  photo_path?: string | null;
};

function PhotoThumb({ path, onOpen }: { path: string; onOpen: () => void }) {
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

  return (
    <button type="button" className="mt-2 block" onClick={onOpen} aria-label="Enlarge photo">
      <img src={src} alt="" className="h-16 w-16 rounded-lg object-cover ring-1 ring-white/10" />
    </button>
  );
}

function PhotoLightbox({ path, onClose }: { path: string; onClose: () => void }) {
  const [src, setSrc] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
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

  return (
    <button
      type="button"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4"
      onClick={onClose}
      aria-label="Close photo"
    >
      <img src={src} alt="" className="max-h-full max-w-full rounded-lg object-contain" onClick={(e) => e.stopPropagation()} />
    </button>
  );
}

export default function ApprovalCard({ item }: { item: ApprovalFeedItem }) {
  const [enlarge, setEnlarge] = useState(false);
  if (!item.approval_card_title) return null;
  const primary = item.approval_viewer_is_actor;
  const bullets = (item.approval_detail_bullets ?? []).filter(
    (line) => line !== item.approval_reason_line && line !== item.approval_when_label,
  );
  return (
    <>
      <article
        className={`owner-oat-highlight rounded-2xl p-4 ${primary ? "ring-1 ring-[var(--accent)]/35" : ""}`}
        data-kind={item.kind}
        data-id={item.id}
      >
        {item.approval_needs_you && (
          <p className="text-xs font-medium uppercase tracking-wide text-[var(--accent)]">This needs you</p>
        )}
        <p className={`text-base font-medium text-[var(--text)] ${item.approval_needs_you ? "mt-1" : ""}`}>{item.approval_card_title}</p>
        {!primary && item.approval_card_subtitle && (
          <p className="mt-0.5 text-sm text-zinc-400">{item.approval_card_subtitle}</p>
        )}
        {item.approval_reason_line && <p className="mt-2 text-sm text-zinc-300">Reason: {item.approval_reason_line}</p>}
        {item.approval_when_label && <p className="mt-1 text-xs text-zinc-500">{item.approval_when_label}</p>}
        {item.photo_path && <PhotoThumb path={item.photo_path} onOpen={() => setEnlarge(true)} />}
        {bullets.length > 0 && (
          <ul className="mt-2 space-y-1 text-[0.9375rem] leading-6 text-[var(--text)]">
            {bullets.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        )}
        {!primary && item.approval_waiting_on && (
          <p className="mt-2 text-xs text-zinc-400">You will be told when it is decided.</p>
        )}
      </article>
      {enlarge && item.photo_path && <PhotoLightbox path={item.photo_path} onClose={() => setEnlarge(false)} />}
    </>
  );
}