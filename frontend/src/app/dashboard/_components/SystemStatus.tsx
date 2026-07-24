"use client";

import { LucideIcon } from "lucide-react";

export default function SystemStatus({ icon: Icon, label, status }: { icon: LucideIcon; label: string; status: string }) {
    return (
        <div className="flex items-center gap-2">
            <Icon className="w-3 h-3 text-text-dim" />
            <span className="text-xs text-text-muted">{label}</span>
            <span className={`w-1.5 h-1.5 rounded-full ml-auto ${status === "connected" ? "bg-success" : "bg-danger"
                }`} />
        </div>
    );
}
