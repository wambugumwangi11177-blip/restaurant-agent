import ChartEmpty, { isEmpty, type ChartStateProps } from "./ChartEmpty";

export type DialTone = "good" | "warn" | "bad";

type Props = ChartStateProps & {
  /** Where the restaurant is, in the same unit as `target` (a percentage of sales). */
  value: number;
  /** The owner's own target: everything below it is the green band. */
  target: number;
  /** The scale's end; default leaves room above both the target and the value. */
  max?: number;
  /** "Out of every KES 100, ingredients" */
  label: string;
  /** The owner's word for it: Fine · Watch · High. */
  word: string;
  tone: DialTone;
  unit?: string;
};

const CX = 100;
const CY = 100;
const R = 78;
const TONE: Record<DialTone, string> = { good: "var(--v-good)", warn: "var(--v-warn)", bad: "var(--v-destructive)" };

const polar = (deg: number, r = R) => [CX + r * Math.cos((deg * Math.PI) / 180), CY - r * Math.sin((deg * Math.PI) / 180)] as const;
/** The angle for a value: the scale runs left (180°) to right (0°). */
const angle = (v: number, max: number) => 180 - Math.min(Math.max(v / max, 0), 1) * 180;
function arc(from: number, to: number): string {
  const [x0, y0] = polar(from);
  const [x1, y1] = polar(to);
  return `M ${x0.toFixed(2)} ${y0.toFixed(2)} A ${R} ${R} 0 0 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`;
}

/** A half-circle gauge: a green band up to the owner's target, an amber band past it, and a marker where the restaurant is. */
export default function Dial({ value, target, max, label, word, tone, unit = "%", state, reason, day, of }: Props) {
  if (isEmpty(state)) return <ChartEmpty state={state} reason={reason} day={day} of={of} height={120} />;
  const top = max ?? Math.max(target * 1.6, value * 1.15, 1);
  const split = angle(target, top);
  const [mx, my] = polar(angle(value, top), R - 22);
  const [tx, ty] = polar(angle(value, top), R + 8);
  return (
    <figure className="text-center">
      <svg role="img" aria-label={`${label}: ${value}${unit}, ${word}. Your target is ${target}${unit}.`} viewBox="0 0 200 122" className="mx-auto w-full max-w-[220px]">
        <path d={arc(180, split)} fill="none" stroke="var(--v-good)" strokeOpacity="0.55" strokeWidth="14" strokeLinecap="butt" />
        <path d={arc(split, 0)} fill="none" stroke="var(--v-warn)" strokeOpacity="0.5" strokeWidth="14" strokeLinecap="butt" />
        <line x1={mx} y1={my} x2={tx} y2={ty} stroke={TONE[tone]} strokeWidth="4" strokeLinecap="round" />
        <circle cx={polar(angle(value, top), R)[0]} cy={polar(angle(value, top), R)[1]} r="7" fill={TONE[tone]} stroke="var(--v-card)" strokeWidth="2.5" />
        <text x={CX} y={CY - 8} textAnchor="middle" fontSize="26" fontWeight="700" fill="var(--v-foreground)">{`${value}${unit}`}</text>
        <text x={CX} y={CY + 10} textAnchor="middle" fontSize="11" fontWeight="700" fill={TONE[tone]}>{word}</text>
      </svg>
      <figcaption className="mt-1 text-[11px] leading-snug text-[var(--v-muted-foreground)]">{label}<br />Your target: {target}{unit}</figcaption>
    </figure>
  );
}
