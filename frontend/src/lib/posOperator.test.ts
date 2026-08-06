/**
 * POS operator persistence (tech-debt D16).
 *
 * The failure this guards against is silent: when the operator is lost, orders
 * still submit successfully and the backend accepts null attribution by design,
 * so nothing surfaces that the accountability trail has gone blank.
 */

import { describe, it, expect, beforeEach } from "vitest";
import { readOperator, writeOperator, clearOperator } from "./posOperator";

const STORAGE_KEY = "chakula_pos_operator";
const AMINA = { id: 42, display_name: "Amina", role: "staff" };

beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();
});

describe("posOperator", () => {
    it("round-trips an operator across a reload", () => {
        writeOperator(AMINA);
        expect(readOperator()).toEqual(AMINA);
    });

    it("returns null when nothing is stored", () => {
        expect(readOperator()).toBeNull();
    });

    it("clears on logout so the next login doesn't inherit the operator", () => {
        writeOperator(AMINA);
        clearOperator();
        expect(readOperator()).toBeNull();
    });

    it("rejects a stored entry with no numeric id", () => {
        // Would otherwise render a name in the header while attributing
        // nothing — the same silent failure as the /pin/verify shape mismatch.
        sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ user_id: 42, display_name: "Amina" }));
        expect(readOperator()).toBeNull();
    });

    it("survives a corrupt stored value", () => {
        sessionStorage.setItem(STORAGE_KEY, "{not json");
        expect(readOperator()).toBeNull();
    });

    it("does not persist to localStorage", () => {
        // sessionStorage only: a tablet left on the counter overnight must not
        // still be ringing up orders as whoever closed last night.
        writeOperator(AMINA);
        expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
        expect(sessionStorage.getItem(STORAGE_KEY)).toBeTruthy();
    });
});
