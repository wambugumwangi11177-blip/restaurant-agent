/** English count phrases: "1 item" vs "3 items". */
export function plural(count: number, singular: string, pluralForm?: string): string {
  const n = Math.abs(Math.round(count));
  const word = n === 1 ? singular : pluralForm ?? `${singular}s`;
  return `${n} ${word}`;
}