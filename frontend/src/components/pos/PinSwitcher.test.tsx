/**
 * PIN quick-switch (tech-debt D16).
 *
 * The point of these tests is the API paths. The backend router mounts only at
 * /api/v1/auth (main.py includes it outside the dual-mount loop), while
 * api.ts's baseURL is the bare host — so an unprefixed path 404s, the roster
 * silently renders "no staff", and the whole feature is dead with green
 * backend tests. That is exactly how it shipped once; these tests pin it.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("@/lib/api", () => ({
    default: { get: vi.fn(), post: vi.fn() },
}));

import api from "@/lib/api";
import { PinSwitcher } from "./PinSwitcher";

const ROSTER = {
    data: { staff: [{ id: 7, display_name: "Amina", role: "staff" }] },
};

beforeEach(() => {
    vi.mocked(api.get).mockReset();
    vi.mocked(api.post).mockReset();
});

async function openSwitcher() {
    const onSwitch = vi.fn();
    render(<PinSwitcher currentOperator={null} onSwitch={onSwitch} />);
    await userEvent.click(screen.getByRole("button", { name: /select staff/i }));
    return onSwitch;
}

describe("PinSwitcher", () => {
    it("fetches the roster from the versioned auth path", async () => {
        vi.mocked(api.get).mockResolvedValue(ROSTER);
        await openSwitcher();

        await waitFor(() => expect(api.get).toHaveBeenCalledWith("/api/v1/auth/pin/roster"));
    });

    it("renders staff returned by the roster", async () => {
        vi.mocked(api.get).mockResolvedValue(ROSTER);
        await openSwitcher();

        expect(await screen.findByRole("button", { name: "Amina" })).toBeTruthy();
        expect(screen.queryByText(/no staff have set up a pin yet/i)).toBeNull();
    });

    it("verifies against the versioned auth path and reports the operator", async () => {
        vi.mocked(api.get).mockResolvedValue(ROSTER);
        vi.mocked(api.post).mockResolvedValue({
            data: { user_id: 7, display_name: "Amina", role: "staff" },
        });
        const onSwitch = await openSwitcher();

        await userEvent.click(await screen.findByRole("button", { name: "Amina" }));
        for (const d of ["4", "2", "4", "2"]) {
            await userEvent.click(screen.getByRole("button", { name: d }));
        }
        await userEvent.click(screen.getByRole("button", { name: /confirm/i }));

        await waitFor(() =>
            expect(api.post).toHaveBeenCalledWith("/api/v1/auth/pin/verify", {
                user_id: 7,
                pin: "4242",
            })
        );
        // Must be normalized to `id` — the POS reads activeOperator.id to stamp
        // attributed_user_id, so passing the backend's raw `user_id` through
        // silently attributes every order to nobody.
        expect(onSwitch).toHaveBeenCalledWith({ id: 7, display_name: "Amina", role: "staff" });
    });

    it("closes on Escape", async () => {
        vi.mocked(api.get).mockResolvedValue(ROSTER);
        await openSwitcher();
        expect(await screen.findByRole("dialog")).toBeTruthy();

        await userEvent.keyboard("{Escape}");

        await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    });

    it("surfaces a roster failure instead of claiming nobody has a PIN", async () => {
        // A failed fetch previously fell through to the empty-roster copy, which
        // reads as a settings problem and sends staff down the wrong path.
        vi.mocked(api.get).mockRejectedValue(new Error("Network Error"));
        await openSwitcher();

        expect(await screen.findByText(/couldn't load the staff list/i)).toBeTruthy();
    });
});
