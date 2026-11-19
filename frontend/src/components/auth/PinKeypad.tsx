"use client";

const KEYS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "", "0", "⌫"] as const;

export default function PinKeypad({
  value,
  onChange,
  disabled,
  ariaLabel = "PIN keypad",
}: {
  value: string;
  onChange: (next: string) => void;
  disabled?: boolean;
  ariaLabel?: string;
}) {
  function press(key: string) {
    if (disabled) return;
    if (key === "⌫") {
      onChange(value.slice(0, -1));
      return;
    }
    if (!key || value.length >= 4) return;
    onChange(`${value}${key}`.slice(0, 4));
  }

  return (
    <div aria-label={ariaLabel} className="grid grid-cols-3 gap-2">
      {KEYS.map((key, index) =>
        key === "" ? (
          <div key={`sp-${index}`} aria-hidden className="min-h-14" />
        ) : (
          <button
            key={key}
            type="button"
            disabled={disabled || (key !== "⌫" && value.length >= 4)}
            onClick={() => press(key)}
            className="flex min-h-14 items-center justify-center rounded-2xl border border-white/15 bg-black/40 text-xl font-semibold text-white active:bg-white/10 disabled:opacity-40"
          >
            {key}
          </button>
        ),
      )}
    </div>
  );
}