/**
 * One calendar day for the floor: Africa/Nairobi.
 *
 * Order timestamps are naive UTC (no Z). Parsing them as local Date in Kenya
 * shifts the day, which is how Orders showed KES 0 while Sales showed another
 * day's takings. Treat naive strings as UTC, then convert to Nairobi.
 *
 * Reservation `reservation_date` is already a YYYY-MM-DD calendar date — compare
 * it to nairobiDate() directly, do not run it through utcNaiveToDate.
 */

export const BUSINESS_TZ = "Africa/Nairobi";

export function nairobiDate(d: Date = new Date()): string {
    return new Intl.DateTimeFormat("en-CA", {
        timeZone: BUSINESS_TZ,
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
    }).format(d);
}

export function utcNaiveToDate(iso: string | null | undefined): Date | null {
    if (!iso) return null;
    const s = String(iso).trim();
    if (!s) return null;
    if (/[zZ]$/.test(s) || /[+-]\d{2}:\d{2}$/.test(s)) {
        const d = new Date(s);
        return Number.isNaN(d.getTime()) ? null : d;
    }
    const normalized = s.replace(" ", "T") + "Z";
    const d = new Date(normalized);
    return Number.isNaN(d.getTime()) ? null : d;
}

export function businessDayOf(iso: string | null | undefined): string | null {
    const d = utcNaiveToDate(iso);
    if (!d) return null;
    return nairobiDate(d);
}

export function isOnBusinessDay(
    iso: string | null | undefined,
    day: string = nairobiDate(),
): boolean {
    return businessDayOf(iso) === day;
}

export function nairobiHour(iso: string | null | undefined): number | null {
    const d = utcNaiveToDate(iso);
    if (!d) return null;
    const hour = new Intl.DateTimeFormat("en-GB", {
        timeZone: BUSINESS_TZ,
        hour: "2-digit",
        hourCycle: "h23",
    }).format(d);
    return parseInt(hour, 10);
}
