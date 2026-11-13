"use client";

import { takePhoto } from "@/lib/capturePhoto";

export default function PhotoField({
  label,
  file,
  onFile,
  optional = false,
}: {
  label: string;
  file: File | null;
  onFile: (file: File | null) => void;
  optional?: boolean;
}) {
  return (
    <div className="text-sm">
      <p>{label}{optional ? " (optional)" : ""}</p>
      <button
        type="button"
        className="mt-1 flex min-h-11 w-full items-center justify-center rounded-full bg-white px-3 font-semibold text-black"
        onClick={async (event) => {
          const photo = await takePhoto().catch(() => null);
          if (photo) {
            onFile(photo);
            return;
          }
          const input = event.currentTarget.parentElement?.querySelector<HTMLInputElement>("input[data-gallery]");
          input?.click();
        }}
      >
        {file ? file.name : "Take a photo"}
      </button>
      <label className="mt-2 inline-flex min-h-11 w-full items-center justify-center rounded-full border border-white/20 px-3 text-zinc-300">
        Or choose from the gallery
        <input
          data-gallery
          type="file"
          accept="image/*"
          className="sr-only"
          onChange={(event) => onFile(event.target.files?.[0] ?? null)}
        />
      </label>
    </div>
  );
}
