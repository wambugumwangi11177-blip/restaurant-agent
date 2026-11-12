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
      <div className="mt-1 flex gap-2">
        <label className="inline-flex min-h-11 flex-1 items-center justify-center rounded-full border border-white/20 px-3">
          {file ? file.name : "Choose a photo"}
          <input
            type="file"
            accept="image/*"
            capture="environment"
            className="sr-only"
            onChange={(event) => onFile(event.target.files?.[0] ?? null)}
          />
        </label>
        <button
          type="button"
          className="min-h-11 rounded-full border border-white/20 px-3"
          onClick={async (event) => {
            const photo = await takePhoto().catch(() => null);
            if (photo) {
              onFile(photo);
              return;
            }
            const input = event.currentTarget.parentElement?.querySelector("input");
            input?.click();
          }}
        >
          Camera
        </button>
      </div>
    </div>
  );
}
