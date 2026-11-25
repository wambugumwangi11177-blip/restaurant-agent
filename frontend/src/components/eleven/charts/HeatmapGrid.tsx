"use client";

const DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export default function HeatmapGrid({
  cells,
}: {
  cells: { dow: number; hour: number; kes: number }[];
}) {
  const max = Math.max(1, ...cells.map((c) => c.kes));
  const map = new Map<string, number>();
  for (const c of cells) {
    map.set(`${c.dow}-${c.hour}`, c.kes);
  }
  return (
    <div className="grid grid-cols-[2rem_repeat(24,minmax(0,1fr))] gap-px text-[9px] text-zinc-500">
      <div />
      {Array.from({ length: 24 }, (_, h) => (
        <div key={h} className="text-center">
          {h % 6 === 0 ? h : ""}
        </div>
      ))}
      {DOW.map((label, dow) => (
        <div key={label} className="contents">
          <span className="flex items-center pr-1">{label}</span>
          {Array.from({ length: 24 }, (_, hour) => {
            const kes = map.get(`${dow}-${hour}`) ?? 0;
            const alpha = 0.15 + 0.85 * (kes / max);
            return (
              <div
                key={`${dow}-${hour}`}
                title={kes ? `${kes.toLocaleString()} KES` : ""}
                className="aspect-square min-h-[10px] rounded-sm"
                style={{ backgroundColor: `rgba(196, 181, 168, ${kes ? alpha : 0.08})` }}
              />
            );
          })}
        </div>
      ))}
    </div>
  );
}