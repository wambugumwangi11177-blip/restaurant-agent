import ChartEmpty, { isEmpty, type ChartStateProps } from "./ChartEmpty";

export type HeatCell = { weekday: number; shift: "day" | "evening"; timesShort: number; ofLast: number; title: string };

type Props = ChartStateProps & { cells: HeatCell[]; label: string };

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const SHIFTS: { key: "day" | "evening"; label: string }[] = [{ key: "day", label: "Day" }, { key: "evening", label: "Evening" }];

/** Weekday by shift: a square darkens the more often that shift came up short. Only shifts that repeat are filled; the rest stay quiet. */
export default function HeatGrid({ cells, label, state, reason, day, of }: Props) {
  if (isEmpty(state)) return <ChartEmpty state={state} reason={reason} day={day} of={of} />;
  const at = (weekday: number, shift: string) => cells.find((c) => c.weekday === weekday && c.shift === shift);
  return (
    <table aria-label={label} className="w-full table-fixed text-center text-[10px]">
      <thead>
        <tr><td className="w-14" />{DAYS.map((d) => <th scope="col" key={d} className="pb-1 font-semibold text-[var(--v-muted-foreground)]">{d}</th>)}</tr>
      </thead>
      <tbody>
        {SHIFTS.map((s) => (
          <tr key={s.key}>
            <th scope="row" className="pr-2 text-right font-semibold text-[var(--v-muted-foreground)]">{s.label}</th>
            {DAYS.map((_, wd) => {
              const c = at(wd, s.key);
              const level = c ? c.timesShort / Math.max(c.ofLast, 1) : 0;
              return (
                <td key={wd} className="p-0.5">
                  <div title={c?.title ?? ""} className="flex h-9 items-center justify-center rounded-md font-bold"
                    style={{ background: c ? `hsl(4 61% 52% / ${0.18 + level * 0.7})` : "var(--v-muted)", color: c && level > 0.55 ? "white" : "var(--v-foreground)" }}>
                    {c ? `${c.timesShort}/${c.ofLast}` : ""}
                  </div>
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
