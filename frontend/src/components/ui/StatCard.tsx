"use client";

interface StatCardProps {
    label: string;
    value: string | number;
    sub?: string;
    color?: string;
    className?: string;
}

export default function StatCard({ label, value, sub, color, className = "" }: StatCardProps) {
    return (
        <div className={`bg-[var(--surface)] border border-[var(--border)] rounded-xl p-4 ${className}`}>
            <p className="text-lg font-bold text-[var(--text)]" style={color ? { color } : undefined}>
                {value}
            </p>
            <p className="text-xs text-[var(--text-dim)] mt-0.5">{label}</p>
            {sub && <p className="text-[10px] mt-1" style={{ color }}>{sub}</p>}
        </div>
    );
}