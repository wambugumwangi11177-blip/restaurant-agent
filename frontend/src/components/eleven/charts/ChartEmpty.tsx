export default function ChartEmpty({ hint }: { hint: string }) {
  return (
    <div
      className="flex min-h-[120px] flex-col items-center justify-center rounded-2xl border border-dashed border-zinc-500/50 bg-zinc-900/20 px-4 py-6 text-center"
      data-testid="chart-empty"
    >
      <p className="text-sm text-zinc-400">{hint}</p>
    </div>
  );
}