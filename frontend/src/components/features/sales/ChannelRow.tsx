"use client";

import { LucideIcon } from "lucide-react";

interface ChannelRowProps {
    icon: LucideIcon;
    label: string;
    count: number;
    total: number;
    color: string;
    formatKES: (v: number) => string;
    nested?: boolean;
}

export default function ChannelRow({ icon: Icon, label, count, total, color, formatKES, nested }: ChannelRowProps) {
    return (
        <div className={`flex items-center gap-3 ${nested ? "pl-4 opacity-70" : ""}`}>
            <Icon className="w-3.5 h-3.5" style={{ color }} />
            <div className="flex-1"><p className="text-xs text-text">{label}</p></div>
            <span className="text-[10px] text-text-dim">{count}</span>
            <span className="text-xs font-semibold text-text w-24 text-right">{formatKES(total)}</span>
        </div>
    );
}
