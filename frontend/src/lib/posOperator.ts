// Persistence for the PIN-verified POS operator (tech-debt D16).
//
// A shared tablet is logged in once per shift under one device account, and the
// operator is who orders get attributed to. Holding that in React state alone
// meant any reload — a service-worker update, mobile Safari evicting a
// backgrounded tab, an accidental refresh — silently reverted to no operator,
// and every subsequent order was stamped attributed_user_id: null. The backend
// accepts null attribution by design (a device that hasn't PIN-switched still
// works), so nothing surfaced the loss.
//
// sessionStorage, not localStorage: attribution should survive a reload but not
// outlive the tab. A tablet left on the counter overnight should not still be
// ringing up orders as whoever closed last night.

export interface StoredOperator {
    id: number;
    display_name: string;
    role: string;
}

const STORAGE_KEY = "chakula_pos_operator";

export function readOperator(): StoredOperator | null {
    if (typeof window === "undefined") return null;
    try {
        const raw = window.sessionStorage.getItem(STORAGE_KEY);
        if (!raw) return null;
        const parsed = JSON.parse(raw) as StoredOperator;
        // Guard the shape: a stored entry missing a numeric id would attribute
        // to nobody while the header still showed a name — the same silent
        // failure the /pin/verify response-shape bug caused.
        if (typeof parsed?.id !== "number") return null;
        return parsed;
    } catch {
        return null;
    }
}

export function writeOperator(operator: StoredOperator): void {
    if (typeof window === "undefined") return;
    try {
        window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(operator));
    } catch {
        // Storage full or blocked (private mode) — attribution degrades to
        // in-memory only, which is the old behavior, not a new failure.
    }
}

/** Clear on logout: the next person to log in on this tablet must not inherit
 * the previous session's operator. The backend rejects cross-tenant attribution
 * anyway, but a same-tenant stale operator would be accepted silently. */
export function clearOperator(): void {
    if (typeof window === "undefined") return;
    try {
        window.sessionStorage.removeItem(STORAGE_KEY);
    } catch {
        // Nothing to do — a failed clear leaves the old value, which the
        // shape guard in readOperator will still accept; acceptable versus
        // throwing during logout.
    }
}
