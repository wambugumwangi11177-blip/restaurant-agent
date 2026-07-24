"use client";

import { motion } from "framer-motion";

interface StatCardProps {
    label: string;
    value: string | number;
    sub?: string;
    color?: string;
    className?: string;
}

export default function StatCard({ label, value, sub, color, className = "" }: StatCardProps) {
    return (
        <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className={`bg-[var(--surface)] border border-[var(--border)] rounded-xl p-4 ${className}`}
        >
            <p className="text-lg font-bold text-[var(--text)]" style={color ? { color } : undefined}>
                {value}
            </p>
            <p className="text-xs text-[var(--text-dim)] mt-0.5">{label}</p>
            {sub && <p className="text-[10px] mt-1" style={{ color }}>{sub}</p>}
        </motion.div>
    );
}
