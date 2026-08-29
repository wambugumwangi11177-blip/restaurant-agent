"use client";

import { LucideIcon } from "lucide-react";

interface PaymentRowProps {
    icon: LucideIcon;
    label: string;
    count: number;
    total: number;
    color: string;
    formatKES: (v: number) => string;
}

export default function PaymentRow({ icon: Icon, label, count, total, color, formatKES }: PaymentRowProps) {
    return (
        <div className="flex items-center gap-3">
            <Icon className="w-4 h-4" style={{ color }} />
            <div className="flex-1"><p className="text-xs text-text">{label}</p></div>
            <span className="text-[10px] text-text-dim">{count} orders</span>
            <span className="text-xs font-semibold text-text w-24 text-right">{formatKES(total)}</span>
        </div>
    );
}
