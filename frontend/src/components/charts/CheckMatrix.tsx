export type MatrixCell = { trick: string; check: string; catches: boolean; count: number };

const TRICKS = ["Cash short", "Sale cancelled", "M-Pesa not on the statement", "Charged under the menu price", "Stock used beyond the recipes"];
const CHECKS = ["Cash count", "Cancelled sales", "M-Pesa check", "Menu price", "Stock count"];

/** Which check catches which trick, with this period's counts in the cells that fired. */
export default function CheckMatrix({ counts, label = "Which check catches which trick" }: { counts: Record<string, number>; label?: string }) {
  const cell = (trick: string, check: string): MatrixCell => {
    const pair: Record<string, string> = {
      "Cash short|Cash count": "cash",
      "Sale cancelled|Cancelled sales": "cancelled",
      "M-Pesa not on the statement|M-Pesa check": "mpesa",
      "Charged under the menu price|Menu price": "price",
      "Stock used beyond the recipes|Stock count": "stock",
    };
    const key = pair[`${trick}|${check}`];
    const n = key ? counts[key] ?? 0 : 0;
    return { trick, check, catches: Boolean(key), count: n };
  };
  const any = Object.values(counts).some((n) => n > 0);
  return (
    <figure className="overflow-x-auto">
      <table aria-label={label} className="w-full min-w-[28rem] text-left text-[11px]">
        <thead>
          <tr>
            <th className="p-1.5 font-bold">Trick</th>
            {CHECKS.map((c) => <th key={c} className="p-1.5 font-bold">{c}</th>)}
          </tr>
        </thead>
        <tbody>
          {TRICKS.map((trick) => (
            <tr key={trick} className="border-t border-[var(--v-border)]">
              <th scope="row" className="p-1.5 font-semibold">{trick}</th>
              {CHECKS.map((check) => {
                const c = cell(trick, check);
                return <td key={check} className="p-1.5">{c.catches ? (c.count > 0 ? <b>{c.count} this period</b> : "Catches it") : "Does not catch it"}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {!any && <figcaption className="mt-1 text-[11px] text-[var(--v-muted-foreground)]">Nothing to look at in this period. A number appears in a cell when that check finds the trick.</figcaption>}
    </figure>
  );
}
