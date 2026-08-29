"use client";

import { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
    variant?: Variant;
    size?: Size;
}

const VARIANT_CLASSES: Record<Variant, string> = {
    primary: "bg-[var(--accent)] text-[#0a0a0a] font-semibold hover:bg-[var(--accent-hover)]",
    secondary: "bg-[var(--surface)] border border-[var(--border)] text-[var(--text)] hover:bg-[var(--surface-hover)]",
    ghost: "text-[var(--text-muted)] hover:text-[var(--text)]",
    danger: "bg-[var(--danger)]/10 border border-[var(--danger)]/30 text-[var(--danger)] hover:bg-[var(--danger)]/20",
};

const SIZE_CLASSES: Record<Size, string> = {
    sm: "px-3 py-1.5 text-xs",
    md: "px-4 py-2 text-sm",
};

export default function Button({
    variant = "primary",
    size = "md",
    className = "",
    type = "button",
    ...rest
}: ButtonProps) {
    return (
        <button
            type={type}
            className={`rounded-lg transition-colors disabled:opacity-60 ${VARIANT_CLASSES[variant]} ${SIZE_CLASSES[size]} ${className}`}
            {...rest}
        />
    );
}
