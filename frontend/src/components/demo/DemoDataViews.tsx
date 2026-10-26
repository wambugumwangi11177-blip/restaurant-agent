"use client";
import { useState } from "react";
import { cell, type Column, type RecordRow } from "@/lib/demo-modules";

export function RecordsTable({
  rows,
  columns,
  caption,
  empty,
}: {
  rows: RecordRow[];
  columns: Column[];
  caption: string;
  empty: string;
}) {
  const [page, setPage] = useState(0);
  const size = 10;
  const current = Math.min(
    page,
    Math.max(0, Math.ceil(rows.length / size) - 1),
  );
  if (!rows.length)
    return (
      <p className="rounded-xl border border-dashed border-[var(--v-border)] p-5 text-sm leading-6 text-[var(--v-muted-foreground)]">
        {empty}
      </p>
    );
  return (
    <div>
      <div className="overflow-x-auto rounded-xl border border-[var(--v-border)]">
        <table className="w-full text-left text-sm">
          <caption className="px-4 py-3 text-left text-sm text-[var(--v-muted-foreground)]">
            {caption}
          </caption>
          <thead className="bg-[var(--v-muted)]">
            <tr>
              {columns.map((c) => (
                <th
                  key={c.key}
                  scope="col"
                  className="whitespace-nowrap px-4 py-3 font-semibold"
                >
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows
              .slice(current * size, (current + 1) * size)
              .map((row, index) => (
                <tr
                  key={String(row.id ?? row.date ?? current * size + index)}
                  className="border-t border-[var(--v-border)]"
                >
                  {columns.map((c) => (
                    <td
                      key={c.key}
                      className="max-w-sm px-4 py-3 align-top leading-6"
                    >
                      {cell(row[c.key], c.format)}
                    </td>
                  ))}
                </tr>
              ))}
          </tbody>
        </table>
      </div>
      {rows.length > size && (
        <div className="mt-3 flex items-center justify-between gap-3 text-sm">
          <span>
            {current * size + 1}–{Math.min((current + 1) * size, rows.length)}{" "}
            of {rows.length}
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={!current}
              onClick={() => setPage(current - 1)}
              className="min-h-10 rounded-lg border border-[var(--v-border)] px-3 disabled:opacity-40"
            >
              Previous
            </button>
            <button
              type="button"
              disabled={(current + 1) * size >= rows.length}
              onClick={() => setPage(current + 1)}
              className="min-h-10 rounded-lg border border-[var(--v-border)] px-3 disabled:opacity-40"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export function ValueChart({
  rows,
  labelKey,
  valueKey,
  title,
  format = "money",
}: {
  rows: RecordRow[];
  labelKey: string;
  valueKey: string;
  title: string;
  format?: Column["format"];
}) {
  const points = rows.filter(
    (r) => typeof r[valueKey] === "number" && Number.isFinite(r[valueKey]),
  );
  const max = Math.max(...points.map((r) => Math.abs(Number(r[valueKey]))), 1);
  if (!points.length || points.every((r) => r[valueKey] === 0))
    return (
      <p className="rounded-xl border border-dashed border-[var(--v-border)] p-5 text-sm text-[var(--v-muted-foreground)]">
        No recorded values to plot for {title.toLowerCase()}.
      </p>
    );
  return (
    <div
      className="space-y-3"
      role="img"
      aria-label={`${title}: ${points.map((r) => `${cell(r[labelKey])} ${cell(r[valueKey], format)}`).join(", ")}`}
    >
      {points.slice(0, 10).map((r, i) => (
        <div key={String(r[labelKey] ?? i)}>
          <div className="mb-1 flex justify-between gap-3 text-sm">
            <span>{cell(r[labelKey])}</span>
            <span className="font-semibold tabular-nums">
              {cell(r[valueKey], format)}
            </span>
          </div>
          <div className="h-2 rounded-full bg-[var(--v-muted)]">
            <div
              className={`h-2 rounded-full ${Number(r[valueKey]) < 0 ? "bg-[var(--v-destructive)]" : "bg-[var(--v-primary)]"}`}
              style={{
                width: `${(Math.abs(Number(r[valueKey])) / max) * 100}%`,
              }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
