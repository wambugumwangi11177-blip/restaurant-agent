"use client";

import { useId, InputHTMLAttributes } from "react";

interface FormFieldProps extends InputHTMLAttributes<HTMLInputElement> {
    label: string;
    srOnlyLabel?: boolean;
}

export default function FormField({ label, srOnlyLabel, id, className, ...inputProps }: FormFieldProps) {
    const generatedId = useId();
    const inputId = id || generatedId;

    return (
        <div className="flex flex-col gap-1">
            <label htmlFor={inputId} className={srOnlyLabel ? "sr-only" : "text-xs text-[#737373]"}>
                {label}
            </label>
            <input id={inputId} className={className} {...inputProps} />
        </div>
    );
}
