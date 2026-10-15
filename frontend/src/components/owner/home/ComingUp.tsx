"use client";
import StateChip from "@/components/owner/StateChip";
import { kes, nairobiTime, plural, shortDay, weekday } from "@/lib/owner/format";
import type { ComingUp as Data } from "@/lib/owner/types";

function Card({ title, block, children }: { title: string; block: Data[keyof Data]; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-4">
      <div className="flex items-center gap-2">
        <h3 className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--v-muted-foreground)]">{title}</h3>
        <StateChip block={block} />
      </div>
      <div className="mt-2 text-xs">{children}</div>
    </div>
  );
}

const Quiet = ({ text }: { text?: string | null }) => <p className="text-[var(--v-muted-foreground)]">{text}</p>;

/** Zone 4 — coming up: the bills, licences, deliveries and bookings that are about to matter. */
export default function ComingUp({ data }: { data: Data }) {
  const { bills, licences, deliveries, bookings } = data;
  return (
    <div className="grid gap-3 md:grid-cols-2">
      <Card title="Bills" block={bills}>
        {bills.items?.length ? (
          <ul className="space-y-1.5">
            {bills.items.map((b) => (
              <li key={`${b.name}-${b.due_on}`} className="flex justify-between gap-3">
                <span>{b.name} · {b.days_away === 0 ? "today" : `in ${plural(b.days_away, "day")}`} ({shortDay(b.due_on)})</span>
                <b className={b.short ? "text-[var(--v-destructive)]" : ""}>{kes(b.amount_kes)}{b.short ? " · short" : ""}</b>
              </li>
            ))}
          </ul>
        ) : <Quiet text={bills.reason ?? "No bills due soon."} />}
      </Card>
      <Card title="Licences" block={licences}>
        {licences.items?.length ? (
          <ul className="space-y-1.5">
            {licences.items.map((l) => (
              <li key={l.name} className="flex justify-between gap-3"><span>{l.name}</span><b className={l.status === "expired" ? "text-[var(--v-destructive)]" : ""}>{l.word} · {shortDay(l.expires_on)}</b></li>
            ))}
          </ul>
        ) : <Quiet text={licences.reason ?? "No licence runs out soon."} />}
      </Card>
      <Card title="Deliveries" block={deliveries}>
        {deliveries.items?.length ? (
          <ul className="space-y-1.5">
            {deliveries.items.map((d) => (
              <li key={`${d.item}-${d.expected_at}`} className="flex justify-between gap-3"><span>{d.item} · {d.supplier}</span><b>{shortDay(d.expected_at.slice(0, 10))}, {nairobiTime(d.expected_at)}</b></li>
            ))}
          </ul>
        ) : <Quiet text={deliveries.reason ?? "No deliveries are on the way."} />}
      </Card>
      <Card title="Bookings" block={bookings}>
        {bookings.next_days?.length ? (
          <>
            <p className="mb-1.5">{bookings.covers_today ? `${plural(bookings.covers_today, "guest")} booked tonight.` : bookings.reason}</p>
            <ul className="space-y-1">
              {bookings.next_days.map((d) => (
                <li key={d.date} className="flex justify-between gap-3"><span>{weekday(d.date)} {shortDay(d.date)}</span><b>{plural(d.bookings, "booking")} · {plural(d.covers, "guest")}</b></li>
              ))}
            </ul>
          </>
        ) : <Quiet text={bookings.reason ?? "No bookings in the next 7 days."} />}
      </Card>
    </div>
  );
}
