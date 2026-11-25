"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import ChartEmpty from "./ChartEmpty";

export default function OwnerChartCard({
  title,
  caption,
  detailHref,
  hasData,
  emptyHint,
  children,
}: {
  title: string;
  caption: string;
  detailHref?: string;
  hasData: boolean;
  emptyHint: string;
  children: ReactNode;
}) {
  const body = hasData ? children : <ChartEmpty hint={emptyHint} />;
  const inner = (
    <article className="owner-glass-panel space-y-3 p-4">
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-sm font-medium text-zinc-100">{title}</h3>
        {detailHref && hasData ? (
          <span className="text-xs text-zinc-400">Details →</span>
        ) : null}
      </div>
      <div className="min-h-[120px] w-full">{body}</div>
      <p className="text-xs leading-5 text-zinc-400">{caption}</p>
    </article>
  );
  if (detailHref && hasData) {
    return (
      <Link href={detailHref} className="block">
        {inner}
      </Link>
    );
  }
  return inner;
}