import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AuthProvider, useAuth } from "./AuthContext";

vi.mock("@/lib/api", () => ({
    default: {
        get: vi.fn(),
        post: vi.fn(),
    },
}));

import api from "@/lib/api";

function Probe() {
    const { user, token, login, logout, isLoading } = useAuth();
    return (
        <div>
            <span data-testid="loading">{String(isLoading)}</span>
            <span data-testid="token">{token ?? "none"}</span>
            <span data-testid="email">{user?.email ?? "none"}</span>
            <button onClick={() => login("owner@example.com", "hunter2")}>login</button>
            <button onClick={() => logout()}>logout</button>
        </div>
    );
}

beforeEach(() => {
    localStorage.clear();
    vi.mocked(api.get).mockReset();
    vi.mocked(api.post).mockReset();
});

describe("AuthProvider", () => {
    it("starts with no user and isLoading false when there is no stored token", async () => {
        render(
            <AuthProvider>
                <Probe />
            </AuthProvider>
        );
        await waitFor(() => expect(screen.getByTestId("loading").textContent).toBe("false"));
        expect(screen.getByTestId("token").textContent).toBe("none");
    });

    it("login stores the token and fetches the user", async () => {
        vi.mocked(api.post).mockResolvedValueOnce({ data: { access_token: "abc123" } });
        vi.mocked(api.get).mockResolvedValueOnce({ data: { id: 1, email: "owner@example.com", role: "admin" } });

        const user = userEvent.setup();
        render(
            <AuthProvider>
                <Probe />
            </AuthProvider>
        );
        await waitFor(() => expect(screen.getByTestId("loading").textContent).toBe("false"));

        await act(async () => {
            await user.click(screen.getByText("login"));
        });

        await waitFor(() => expect(screen.getByTestId("token").textContent).toBe("abc123"));
        expect(screen.getByTestId("email").textContent).toBe("owner@example.com");
        expect(localStorage.getItem("access_token")).toBe("abc123");
        expect(api.post).toHaveBeenCalledWith("/api/v1/auth/login", {
            email: "owner@example.com",
            password: "hunter2",
        });
    });

    it("logout clears the token, user, and localStorage", async () => {
        vi.mocked(api.post).mockResolvedValueOnce({ data: { access_token: "abc123" } });
        vi.mocked(api.get).mockResolvedValueOnce({ data: { id: 1, email: "owner@example.com", role: "admin" } });

        const user = userEvent.setup();
        render(
            <AuthProvider>
                <Probe />
            </AuthProvider>
        );
        await waitFor(() => expect(screen.getByTestId("loading").textContent).toBe("false"));
        await act(async () => {
            await user.click(screen.getByText("login"));
        });
        await waitFor(() => expect(screen.getByTestId("token").textContent).toBe("abc123"));

        await act(async () => {
            await user.click(screen.getByText("logout"));
        });

        expect(screen.getByTestId("token").textContent).toBe("none");
        expect(screen.getByTestId("email").textContent).toBe("none");
        expect(localStorage.getItem("access_token")).toBeNull();
    });
});
