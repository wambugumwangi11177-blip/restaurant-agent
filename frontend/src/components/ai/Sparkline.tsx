"use client";

/**
 * frontend/src/components/ai/Sparkline.tsx
 * A dependency-free trend line. No chart library is installed in this app, so
 * the Overview's Performance panel draws its Revenue/Orders lines here as a
 * scaled inline SVG polyline (optionally with a soft area fill).
 */

interface SparklineProps {
    values: number[];
    stroke?: string;
    fill?: boolean;
    height?: number;
    ariaLabel: string;
}

export function Sparkline({
    values,
    stroke = "var(--accent)",
    fill = true,
    height = 56,
    ariaLabel,
}: SparklineProps) {
    if (!values || values.length === 0) return null;

    const W = 100;
    const H = 32;
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = max - min || 1;
    const stepX = values.length > 1 ? W / (values.length - 1) : W;

    const pts = values.map((v, i) => {
        const x = i * stepX;
        const y = H - ((v - min) / range) * (H - 3) - 1.5;
        return `${x.toFixed(2)},${y.toFixed(2)}`;
    });
    const line = pts.join(" ");
    const area = `0,${H} ${line} ${W},${H}`;

    const last = pts[pts.length - 1].split(",").map(Number);

    return (
        <svg
            viewBox={`0 0 ${W} ${H}`}
            className="w-full block"
            style={{ height }}
            role="img"
            aria-label={ariaLabel}
            preserveAspectRatio="none"
        >
            <title>{ariaLabel}</title>
            {fill && <polygon points={area} fill={stroke} opacity={0.12} />}
            <polyline
                points={line}
                fill="none"
                stroke={stroke}
                strokeWidth={1.6}
                strokeLinejoin="round"
                strokeLinecap="round"
                vectorEffect="non-scaling-stroke"
            />
            {values.length > 1 && (
                <circle cx={last[0]} cy={last[1]} r={1.8} fill={stroke} />
            )}
        </svg>
    );
}
