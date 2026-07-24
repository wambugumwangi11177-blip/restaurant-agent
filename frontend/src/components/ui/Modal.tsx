"use client";

import { ReactNode, useEffect, useRef } from "react";
import { X } from "lucide-react";

interface ModalProps {
    label: string;
    onClose: () => void;
    children: ReactNode;
    className?: string;
}

const FOCUSABLE_SELECTOR =
    'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

export default function Modal({ label, onClose, children, className = "" }: ModalProps) {
    const containerRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        const container = containerRef.current;
        const focusable = container?.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR);
        focusable?.[0]?.focus();

        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === "Escape") {
                onClose();
                return;
            }
            if (e.key !== "Tab" || !container) return;

            const items = Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
            if (items.length === 0) return;
            const first = items[0];
            const last = items[items.length - 1];

            if (e.shiftKey && document.activeElement === first) {
                e.preventDefault();
                last.focus();
            } else if (!e.shiftKey && document.activeElement === last) {
                e.preventDefault();
                first.focus();
            }
        };

        document.addEventListener("keydown", handleKeyDown);
        return () => document.removeEventListener("keydown", handleKeyDown);
    }, [onClose]);

    return (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/60" onClick={onClose}>
            <div
                ref={containerRef}
                role="dialog"
                aria-modal="true"
                aria-label={label}
                className={`w-full max-w-md rounded-xl border border-[var(--border)] bg-[#0f0f0f] p-5 space-y-4 ${className}`}
                onClick={(e) => e.stopPropagation()}
            >
                <div className="flex items-start justify-between gap-3">
                    <h3 className="text-sm font-semibold text-[var(--text)]">{label}</h3>
                    <button onClick={onClose} aria-label="Close dialog" className="text-[var(--text-dim)] hover:text-[var(--text)]">
                        <X className="w-4 h-4" />
                    </button>
                </div>
                {children}
            </div>
        </div>
    );
}
