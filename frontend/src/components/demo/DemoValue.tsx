import Link from "next/link";
import { fmtKes } from "@/lib/format";
export type DemoRoi = {
  potential_daily: number;
  assumption: string;
  opportunities: {
    id: string;
    area: string;
    title: string;
    why: string;
    value: number;
  }[];
};
export default function DemoValue({ roi }: { roi: DemoRoi }) {
  return (
    <section className="rounded-2xl bg-[var(--v-primary)] p-6 text-[var(--v-primary-foreground)] sm:p-8">
      <p className="text-xs uppercase tracking-widest opacity-80">
        See the value · understand the why
      </p>
      <h2 className="font-display mt-3 text-4xl">
        {fmtKes(roi.potential_daily)}{" "}
        <span className="text-xl">potential / day</span>
      </h2>
      <p className="mt-3 max-w-2xl text-sm opacity-85">
        Three practical opportunities in this sample restaurant. Open the
        evidence, test a decision, and ask OS to explain it.
      </p>
      <div className="mt-6 grid gap-3 sm:grid-cols-3">
        {roi.opportunities.map((x) => (
          <Link
            key={x.id}
            href={`/demo/${x.area}`}
            className="rounded-xl border border-white/25 p-4 hover:bg-white/10"
          >
            <p className="text-sm font-semibold">{x.title}</p>
            <p className="font-display my-2 text-2xl">{fmtKes(x.value)}</p>
            <p className="text-xs leading-5 opacity-85">{x.why}</p>
            <p className="mt-3 text-xs">See evidence →</p>
          </Link>
        ))}
      </div>
      <p className="mt-5 text-xs opacity-80">{roi.assumption}</p>
    </section>
  );
}
